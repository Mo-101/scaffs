"""Signal Priority Queue, Quality Gating, and Multi-Strategy Router for Scaffs.

Implements the multi-criteria signal intake, absolute quality gating,
two-axis strategy routing, position collision detection, and execution
dispatch with deterministic clientOrderId idempotency.
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg

_PAPER_SESSIONS_DIR = Path(__file__).resolve().parents[2] / "paper_sessions"

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"

from src.trading.strategy_binding import allowed_workers

_ARCHIVE_PRODUCERS = {"archive", "archived", "backfill", "historical", "research_archive"}
_ARCHIVE_CRITERIA_FLAGS = {"archive", "archived", "backfill", "historical"}


def validate_signal_source_role(
    producer: str,
    source_signal_id: Optional[str],
    criteria: Dict[str, Any],
) -> Optional[str]:
    clean_producer = str(producer or "").strip().lower()
    if clean_producer in _ARCHIVE_PRODUCERS:
        return f"producer '{producer}' is archive/backfill data and cannot enter the live execution queue"

    source_role = str(criteria.get("source_role") or criteria.get("source") or "").strip().lower()
    if source_role in _ARCHIVE_CRITERIA_FLAGS:
        return f"source role '{source_role}' is archive/backfill data and cannot enter the live execution queue"

    if clean_producer == "idim_ikang" and not str(source_signal_id or "").strip():
        return "producer 'idim_ikang' must include source_signal_id from the upstream live signal"

    return None


@dataclass
class QueuedSignal:
    id: str
    source_signal_id: Optional[str]
    producer: str
    symbol: str
    side: str
    timeframe: str
    raw_score: float
    criteria_vector: Dict[str, Any]
    topsis_score: Optional[float]
    target_strategy: str
    status: str
    rejection_reason: Optional[str]
    execution_order_id: Optional[str]
    execution_client_order_id: Optional[str]
    ttl_seconds: int
    created_at: datetime
    dispatched_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ─── Two-Axis Strategy Router ──────────────────────────────────────────────────

def route_signal(
    symbol: str,
    side: str,
    timeframe: str,
    raw_score: float,
    criteria: Dict[str, Any],
) -> Tuple[str, float]:
    """Route a candidate signal to the target strategy vehicle.

    Axes:
      1. Funding-Rate Basis Divergence -> Morning Glory
      2. Low ADX / Ranging Regime -> Bounded Grid Futures
      3. Directional Momentum -> Time-Based Rebalancing (5m, 10m, 15m)
    """
    is_funding = criteria.get("is_funding", False) or "funding" in str(criteria.get("family", "")).lower()
    regime = str(criteria.get("regime", "")).upper()
    adx = float(criteria.get("adx14", 30.0))
    volatility = float(criteria.get("volatility", 1.0))

    # Axis 1: Funding Divergence -> Morning Glory worker
    if is_funding or abs(float(criteria.get("funding_rate", 0.0))) > 0.0005:
        return "morning_glory", 0.95

    # Axis 2: Bounded Grid (Range-bound, non-trending oscillation)
    if regime in ("RANGING", "SIDEWAYS") or (adx < 22.0 and timeframe in ("tick", "1m", "5m")):
        # Lower volatility gets 10x; higher gets 5x.
        return "grid_futures_10x" if volatility < 1.5 else "grid_futures_5x", 0.90

    # Axis 3: Directional Momentum -> equal-weight rebalancer
    return "rebalance_equal_weight_v1", 0.85


# ─── Multi-Criteria TOPSIS Ranker ──────────────────────────────────────────────

def rank_signals_topsis(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute relative TOPSIS closeness coefficient for a batch of candidate signals.

    Criteria:
      - Confidence / Raw Score (benefit, weight=0.35)
      - Freshness (cost/lower age is better, weight=0.25)
      - Regime Fit (benefit, weight=0.25)
      - Volatility Stretch (benefit, weight=0.15)
    """
    if not signals:
        return []
    if len(signals) == 1:
        signals[0]["topsis_score"] = 1.0
        return signals

    # Weights
    weights = [0.35, 0.25, 0.25, 0.15]

    # Extract matrix
    matrix = []
    for s in signals:
        crit = s.get("criteria_vector") or {}
        score = float(s.get("raw_score") or 60.0)
        age_sec = max(0.0, (datetime.now(timezone.utc) - s["created_at"]).total_seconds())
        freshness_score = max(0.0, 100.0 - (age_sec * 0.5))  # Higher is fresher
        regime_fit = float(crit.get("regime_fit", 75.0))
        vol_score = min(100.0, float(crit.get("vol_ratio", 1.0)) * 50.0)
        matrix.append([score, freshness_score, regime_fit, vol_score])

    # Vector normalization
    n_rows = len(matrix)
    n_cols = len(weights)
    norm_matrix = [[0.0] * n_cols for _ in range(n_rows)]

    for j in range(n_cols):
        col_sum_sq = sum(matrix[i][j] ** 2 for i in range(n_rows))
        denom = math.sqrt(col_sum_sq) if col_sum_sq > 0 else 1.0
        for i in range(n_rows):
            norm_matrix[i][j] = (matrix[i][j] / denom) * weights[j]

    # Determine Ideal Best (max) and Ideal Worst (min)
    ideal_best = [max(norm_matrix[i][j] for i in range(n_rows)) for j in range(n_cols)]
    ideal_worst = [min(norm_matrix[i][j] for i in range(n_rows)) for j in range(n_cols)]

    # Compute Euclidean Distances & Closeness
    for i in range(n_rows):
        d_best = math.sqrt(sum((norm_matrix[i][j] - ideal_best[j]) ** 2 for j in range(n_cols)))
        d_worst = math.sqrt(sum((norm_matrix[i][j] - ideal_worst[j]) ** 2 for j in range(n_cols)))
        total_d = d_best + d_worst
        closeness = d_worst / total_d if total_d > 0 else 0.5
        signals[i]["topsis_score"] = round(closeness, 4)

    # Sort descending by topsis_score
    return sorted(signals, key=lambda x: x.get("topsis_score", 0.0), reverse=True)


# ─── Queue Operations & Database Persistence ───────────────────────────────────

class SignalQueueManager:
    """Manages signal queuing, quality gating, collision resolution, and execution."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DSN

    def enqueue_signal(
        self,
        symbol: str,
        side: str,
        producer: str = "scaffs_picker",
        timeframe: str = "5m",
        raw_score: float = 65.0,
        source_signal_id: Optional[str] = None,
        criteria_vector: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Validate, route, and persist a new candidate signal into the queue."""
        clean_sym = symbol.upper().replace("-", "").replace("/", "")
        clean_side = side.upper()
        crit = criteria_vector or {}

        # 1. Absolute Quality Gate Check
        if raw_score < 60.0:
            return {
                "ok": False,
                "status": "REJECTED_QUALITY_GATE",
                "reason": f"Raw score ({raw_score:.2f}) is below absolute cutoff (60.00)",
            }

        role_error = validate_signal_source_role(producer, source_signal_id, crit)
        if role_error:
            return {
                "ok": False,
                "status": "REJECTED_SOURCE_ROLE",
                "reason": role_error,
            }

        # 2. Strategy Routing -> execution worker target
        target_strategy, route_conf = route_signal(clean_sym, clean_side, timeframe, raw_score, crit)
        if target_strategy not in allowed_workers():
            return {
                "ok": False,
                "status": "REJECTED_UNSUPPORTED_STRATEGY",
                "reason": f"worker '{target_strategy}' is not in the canonical allowlist",
            }
        # Record canonical identity for UI/audit without changing DB columns.
        from src.trading.strategy_binding import binding_for_worker

        binding = binding_for_worker(target_strategy)
        crit["route_confidence"] = route_conf
        crit["canonical_strategy_id"] = binding.canonical_id
        crit["strategy_profile"] = binding.profile
        crit["canonical_id"] = (
            binding.canonical_id if binding.profile is None else f"{binding.canonical_id}:{binding.profile}"
        )
        queue_id = str(uuid.uuid4())

        # 3. Insert into PostgreSQL
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trading.signal_queue (
                    id, source_signal_id, producer, symbol, side, timeframe,
                    raw_score, criteria_vector, target_strategy, status, ttl_seconds
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s::jsonb, %s, 'PENDING', %s
                ) RETURNING id, created_at;
                """,
                (
                    queue_id,
                    source_signal_id,
                    producer,
                    clean_sym,
                    clean_side,
                    timeframe,
                    raw_score,
                    json.dumps(crit),
                    target_strategy,
                    ttl_seconds,
                ),
            )
            res = cur.fetchone()
            conn.commit()

        logger.info(
            "Enqueued signal [%s] %s %s -> %s (score: %.2f)",
            queue_id,
            clean_sym,
            clean_side,
            target_strategy,
            raw_score,
        )

        return {
            "ok": True,
            "id": queue_id,
            "symbol": clean_sym,
            "side": clean_side,
            "target_strategy": target_strategy,
            "status": "PENDING",
            "ttl_seconds": ttl_seconds,
            "created_at": res[1].isoformat() if res else None,
        }

    def clean_expired_signals(self) -> int:
        """Mark stale unexecuted signals as EXPIRED in the queue."""
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE paper_trading.signal_queue
                SET status = 'EXPIRED',
                    rejection_reason = 'TTL expired before worker pickup'
                WHERE status = 'PENDING'
                  AND NOW() > (created_at + (ttl_seconds || ' seconds')::interval);
                """
            )
            expired_count = cur.rowcount
            conn.commit()
        return expired_count

    def get_pending_batch(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch and rank active pending signals using TOPSIS."""
        self.clean_expired_signals()
        signals = []
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_signal_id, producer, symbol, side, timeframe,
                       raw_score, criteria_vector, target_strategy, created_at, ttl_seconds
                FROM paper_trading.signal_queue
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (limit,),
            )
            for r in cur.fetchall():
                signals.append({
                    "id": str(r[0]),
                    "source_signal_id": r[1],
                    "producer": r[2],
                    "symbol": r[3],
                    "side": r[4],
                    "timeframe": r[5],
                    "raw_score": float(r[6]) if r[6] is not None else 60.0,
                    "criteria_vector": r[7] if isinstance(r[7], dict) else json.loads(r[7] or "{}"),
                    "target_strategy": r[8],
                    "created_at": r[9],
                    "ttl_seconds": r[10],
                })

        # Multi-criteria ranking
        ranked = rank_signals_topsis(signals)
        return ranked

    def check_position_collision(self, symbol: str, incoming_side: str) -> Tuple[bool, str]:
        """Verify if incoming signal collides with current open inventory.

        Returns (can_execute, reason).
        """
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client, BinanceFuturesConfig

        client = get_binance_futures_client(BinanceFuturesConfig.from_env())
        try:
            positions = client.get_positions(symbol=symbol)
            for p in positions:
                amt = float(p.get("positionAmt", 0.0))
                if amt != 0.0:
                    current_side = "BUY" if amt > 0 else "SELL"
                    if current_side != incoming_side.upper():
                        return False, f"Opposing position open ({amt} {symbol} {current_side}). Signal {incoming_side} blocked to prevent unmanaged flip-flop."
                    else:
                        return True, f"Scale-in permissible on existing {current_side} position."
        except Exception as e:
            logger.warning("Could not query live position risk for collision check (%s): %s", symbol, e)

        return True, "Flat inventory — execution clear."

    def _target_leverage(self, target_strategy: str) -> int:
        if target_strategy.endswith("_10x"):
            return 10
        if target_strategy.endswith("_5x"):
            return 5
        if target_strategy.startswith("rebalance"):
            return 5
        return 1

    def _order_type_for_strategy(self, target_strategy: str) -> str:
        # Grid signals become working-limit orders; all others use market.
        if target_strategy.startswith("grid_futures_"):
            return "LIMIT"
        return "MARKET"

    def dispatch_queued_signal(
        self,
        queue_id: str,
        quantity: Optional[float] = None,
        notional_usd: float = 100.0,
    ) -> Dict[str, Any]:
        """Dispatch a ranked queued signal through the risk gate to Binance."""
        from src.trading.connectors.binance.binance_testnet_executor import BinanceTestnetExecutor
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client
        from src.trading.trade_intent import TradeIntent

        # 1. Fetch signal from DB
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, side, status, topsis_score, raw_score, target_strategy, created_at, ttl_seconds, criteria_vector
                FROM paper_trading.signal_queue
                WHERE id = %s;
                """,
                (queue_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": f"Queued signal {queue_id} not found."}
            if row[2] != "PENDING":
                return {"ok": False, "error": f"Signal {queue_id} has already transitioned to status '{row[2]}'"}

        symbol, side, status, topsis_score, raw_score, strategy, created_at, ttl, criteria_raw = row
        criteria = criteria_raw if isinstance(criteria_raw, dict) else json.loads(criteria_raw or "{}")
        clean_sym = symbol.upper()
        side_norm = side.upper()
        trade_side = "BUY" if side_norm in {"LONG", "BUY"} else "SELL"

        # 2. Position Collision Check
        can_exec, collision_note = self.check_position_collision(clean_sym, trade_side)
        if not can_exec:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET status = 'COLLISION_BLOCKED',
                        rejection_reason = %s,
                        completed_at = NOW()
                    WHERE id = %s;
                    """,
                    (collision_note, queue_id),
                )
                conn.commit()
            return {"ok": False, "status": "COLLISION_BLOCKED", "reason": collision_note}

        # 3. Risk/execution environment defaults tuned for $100 signal notional.
        os.environ.setdefault("MAX_TRADE_NOTIONAL_USDT", "1000")
        os.environ.setdefault("MAX_POSITION_NOTIONAL_USDT", "10000")
        os.environ.setdefault("MAX_LEVERAGE", "10")
        os.environ.setdefault("MIN_AVAILABLE_BALANCE_USDT", "1")
        os.environ.setdefault("MAX_OPEN_POSITIONS", "100")
        os.environ.setdefault("TRADE_COOLDOWN_SECONDS", "0")
        os.environ.setdefault("MAX_MARKET_DATA_AGE_SECONDS", "1000")
        os.environ.setdefault("ALLOWED_SYMBOLS", "BTC-USDT,ETH-USDT,SOL-USDT,BNB-USDT")

        # 4. Compute price and requested leverage
        client = get_binance_futures_client()
        ticker_px = client.get_ticker_price(clean_sym)
        if ticker_px <= 0:
            ticker_px = 1.0

        requested_leverage = int(criteria.get("requested_leverage") or self._target_leverage(strategy))

        # 5. Enforce confirmed leverage invariant: attempt the target, but if an
        # existing position forces a different leverage we use it rather than abort.
        try:
            client.set_leverage(clean_sym, requested_leverage)
        except Exception:
            pass  # will verify below and adjust if needed

        confirmed_leverage = client.get_symbol_leverage(clean_sym)
        if confirmed_leverage != requested_leverage:
            logger.warning(
                "LEVERAGE mismatch for %s: wanted %sx, got %sx; using confirmed %sx",
                clean_sym, requested_leverage, confirmed_leverage, confirmed_leverage,
            )
            requested_leverage = confirmed_leverage

        # 6. Calculate quantity (rounded up to symbol precision) and verify actual notional
        if quantity is None:
            precision = client.get_quantity_precision(clean_sym)
            step = 10 ** -precision
            raw_qty = notional_usd / ticker_px
            quantity = math.ceil(raw_qty / step) * step
            quantity = round(quantity, precision)

        actual_notional = quantity * ticker_px
        if actual_notional < 0.9 * notional_usd or actual_notional > 1.1 * notional_usd:
            sizing = (
                f"NOTIONAL_STEP_TOO_COARSE: target ${notional_usd} maps to ${actual_notional:.2f} "
                f"(quantity {quantity} @ {ticker_px:.2f})"
            )
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET status = 'EXECUTION_FAILED',
                        rejection_reason = %s,
                        completed_at = NOW()
                    WHERE id = %s;
                    """,
                    (sizing, queue_id),
                )
                conn.commit()
            return {"ok": False, "status": "EXECUTION_FAILED", "queue_id": queue_id, "reason": sizing}

        # 7. Build exchange-agnostic TradeIntent
        order_type = self._order_type_for_strategy(strategy)
        limit_price: Optional[float] = None
        if order_type == "LIMIT":
            offset = 0.002  # 0.2% working limit around mark
            tick = client.get_price_tick_size(clean_sym)
            if trade_side == "BUY":
                raw_price = ticker_px * (1 - offset)
                limit_price = round(math.floor(raw_price / tick) * tick, 8)
            else:
                raw_price = ticker_px * (1 + offset)
                limit_price = round(math.ceil(raw_price / tick) * tick, 8)

        timestamp = datetime.now(timezone.utc).isoformat()
        intent = TradeIntent(
            intent_id=queue_id,
            strategy_id=strategy,
            symbol=clean_sym,
            side=trade_side,
            quantity=quantity,
            notional=notional_usd,
            order_type=order_type,
            limit_price=limit_price,
            reduce_only=False,
            reason=f"signal {queue_id}",
            signal_timestamp=timestamp,
            market_snapshot={
                "price": ticker_px,
                "leverage": confirmed_leverage,
                "timestamp": timestamp,
                "source": "binance_testnet",
            },
            trading_env="binance_testnet",
        )

        # 6. Run through Step 4 risk gate and (if approved) Step 5 live execution
        session_dir = _PAPER_SESSIONS_DIR / "signal_queue"
        session_dir.mkdir(parents=True, exist_ok=True)

        try:
            executor = BinanceTestnetExecutor(client=client)
            executor.execution_enabled = True  # signal dispatch is an explicit live execution
            result = executor.submit(intent, session_dir=session_dir)

            if result.status == "SUBMITTED" or result.status == "FILLED":
                status = "DISPATCHED"
                order_id = result.exchange_order_id or ""
                client_order_id = queue_id[:32]
                with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE paper_trading.signal_queue
                        SET status = 'DISPATCHED',
                            execution_order_id = %s,
                            execution_client_order_id = %s,
                            topsis_score = %s,
                            dispatched_at = NOW(),
                            completed_at = NOW()
                        WHERE id = %s;
                        """,
                        (order_id, client_order_id, topsis_score, queue_id),
                    )
                    conn.commit()

                logger.info("Successfully dispatched signal [%s] -> %s %s", queue_id, result.status, order_id)
                return {
                    "ok": True,
                    "status": status,
                    "queue_id": queue_id,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "execution_result": result.to_dict(),
                }

            # Risk or execution rejected/failed
            failure_reason = str(result.error or result.status)
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET status = 'EXECUTION_FAILED',
                        rejection_reason = %s,
                        completed_at = NOW()
                    WHERE id = %s;
                    """,
                    (failure_reason, queue_id),
                )
                conn.commit()

            logger.warning("Signal [%s] failed at risk/execution: %s", queue_id, failure_reason)
            return {
                "ok": False,
                "status": "EXECUTION_FAILED",
                "queue_id": queue_id,
                "reason": failure_reason,
                "execution_result": result.to_dict(),
            }
        except Exception as exc:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET status = 'EXECUTION_FAILED',
                        rejection_reason = %s,
                        completed_at = NOW()
                    WHERE id = %s;
                    """,
                    (str(exc), queue_id),
                )
                conn.commit()
            raise
