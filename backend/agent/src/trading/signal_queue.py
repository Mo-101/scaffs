"""Signal Priority Queue, Quality Gating, and Multi-Strategy Router for Scaffs.

Implements the multi-criteria signal intake, absolute quality gating,
two-axis strategy routing, position collision detection, and execution
dispatch with deterministic clientOrderId idempotency.
"""

from __future__ import annotations

import hashlib
import hmac
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
from psycopg import errors as psycopg_errors
from psycopg.types.json import Json

logger = logging.getLogger(__name__)

_PAPER_SESSIONS_DIR = Path(__file__).resolve().parents[2] / "paper_sessions"

def _get_default_dsn() -> str:
    from src.db_dsn import resolve_dsn

    return resolve_dsn()

DEFAULT_DSN = _get_default_dsn()

from src.trading.strategy_binding import allowed_workers

_ARCHIVE_PRODUCERS = {"archive", "archived", "backfill", "historical", "research_archive"}
_ARCHIVE_CRITERIA_FLAGS = {"archive", "archived", "backfill", "historical"}

# Only these producer identities may enqueue signals. An unrecognized producer
# is rejected outright rather than silently trusted -- this is a proportionate,
# in-file tightening; real cryptographic producer trust would require a
# per-caller identity in the auth layer, which does not exist today.
_KNOWN_PRODUCERS = {"scaffs_picker", "scaffs_native", "idim_ikang", "scaffs_manual"}

# Absolute admission floor, mirrored from paper_session_routes._ABSOLUTE_SCORE_FLOOR.
# Reused as the fixed "ideal worst" anchor for the batch-independent quality score.
_ABSOLUTE_SCORE_FLOOR = 60.0

# Margin mode required for every dispatch. Fixed system policy -- not something
# a signal/criteria_vector can override. See dispatch_queued_signal.
REQUIRED_MARGIN_TYPE = "ISOLATED"

_CLAIM_SECRET_ENV = "SIGNAL_QUEUE_CLAIM_SECRET"
_CLAIM_SECRET_FILE_ENV = "SIGNAL_QUEUE_CLAIM_SECRET_FILE"
_DEV_FALLBACK_CLAIM_SECRET = "scaffs-signal-queue-insecure-dev-secret"

# Statuses in which a queued signal is still in flight (not yet terminal).
_ACTIVE_STATUSES = {"PENDING", "CLAIMED"}
# Statuses where a LIMIT entry order exists on the exchange and may still
# need fill-detection/protection-attachment/TTL-cancellation -- queried by
# reconcile_pending_entries(). DISPATCHED is no longer terminal: it now means
# "entry placed, not yet confirmed filled" as often as it means "filled and
# protected" (the latter case short-circuits straight to PROTECTED instead).
_RESTING_ENTRY_STATUSES = {"DISPATCHED", "PARTIALLY_FILLED", "PROTECTION_FAILED"}
# Terminal statuses where an order was actually placed/filled -- a signal
# that reached one of these must NOT be treated as retry-eligible.
_EXECUTED_TERMINAL_STATUSES = {"DISPATCHED", "PARTIALLY_FILLED", "PROTECTED", "PROTECTION_FAILED"}
# Default cancel-on-TTL window for a resting, unfilled LIMIT entry, when the
# caller doesn't specify one. Distinct from ttl_seconds, which only gates
# PENDING/CLAIMED claim-eligibility before an order is ever placed.
_DEFAULT_ENTRY_TTL_SECONDS = 900

# Hard ceiling on risk_pct-based sizing: no single dispatch may risk more than
# this fraction of available equity, regardless of what a signal/caller
# requests. Env-overridable since "sane default" varies by account size/risk
# appetite, but always enforced -- risk_pct sizing has no other ceiling of its
# own (the Step 4 notional/leverage gate is a backstop, not a risk-fraction cap).
_MAX_RISK_PCT_PER_TRADE = float(os.getenv("MAX_RISK_PCT_PER_TRADE", "0.02"))

# Cost buffer folded into risk_pct sizing's stop distance so a worst-case
# stop-out (fees both sides + fill slippage past the trigger) doesn't realize
# a larger loss than the intended risk budget. 0.001 round-trip fee matches
# the fee_rate=0.0005-per-side convention already used elsewhere in this repo
# (e.g. start_all_services.py's paper sessions); 0.0005 slippage is a
# conservative default for a stop-market fill on a liquid perpetual.
_DEFAULT_ROUND_TRIP_FEE_RATE = 0.001
_DEFAULT_STOP_SLIPPAGE_PCT = 0.0005


def _claim_signing_secret() -> bytes:
    """Key for HMAC claim receipts. Reuses the existing API_AUTH_KEY convention
    (see api_server.py's _configured_api_key()) so most deployments need no new
    configuration; falls back to a logged insecure dev-only secret otherwise.
    """
    secret = (os.getenv(_CLAIM_SECRET_ENV) or os.getenv("API_AUTH_KEY") or "").strip()
    if not secret:
        secret_file = os.getenv(_CLAIM_SECRET_FILE_ENV) or os.getenv("API_AUTH_KEY_FILE")
        if secret_file:
            try:
                secret = Path(secret_file).read_text(encoding="utf-8").strip()
            except OSError:
                secret = ""
    if not secret:
        logger.warning(
            "Neither %s nor API_AUTH_KEY is configured; using an insecure "
            "development-only claim-token secret.",
            _CLAIM_SECRET_ENV,
        )
        secret = _DEV_FALLBACK_CLAIM_SECRET
    return secret.encode("utf-8")


def _make_claim_token(queue_id: str, claimed_at: datetime) -> str:
    msg = f"{queue_id}|{claimed_at.isoformat()}".encode("utf-8")
    return hmac.new(_claim_signing_secret(), msg, hashlib.sha256).hexdigest()


def _parse_signal_timestamp(raw: Optional[str]) -> Optional[datetime]:
    """Parse an upstream-supplied signal generation timestamp defensively.

    Returns None (never "now") on missing/malformed input so "producer didn't
    supply one" stays distinguishable from a real value at read time.
    """
    if not raw:
        return None
    try:
        text = str(raw).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError) as e:
        logger.warning("Could not parse signal_timestamp %r: %s", raw, e)
        return None


def _resolve_limit_price(
    trade_side: str,
    mark: float,
    caller_entry: Optional[float],
    tick: float,
) -> float:
    """Resolve the LIMIT entry price. Every dispatch is a LIMIT entry now --
    never MARKET -- so every strategy needs a concrete entry price, not just
    grid (which previously had the only LIMIT-pricing logic in this file).

    Prefers a caller-supplied `criteria["entry"]` when it's on the correct
    side of mark for the trade direction (this field was already captured
    into range_metadata for audit purposes but never actually used to price
    the order -- a confirmed bug fix). Falls back to the pre-existing 0.2%
    offset-from-mark, tick-rounded scheme (previously grid-only) otherwise.
    """
    if caller_entry is not None:
        try:
            entry = float(caller_entry)
        except (TypeError, ValueError):
            entry = None
        if entry is not None and entry > 0:
            on_correct_side = entry < mark if trade_side == "BUY" else entry > mark
            if on_correct_side:
                if trade_side == "BUY":
                    return round(math.floor(entry / tick) * tick, 8)
                return round(math.ceil(entry / tick) * tick, 8)
            logger.warning(
                "criteria['entry']=%.8f is not on the correct side of mark %.8f for %s; "
                "falling back to offset-from-mark pricing.",
                entry, mark, trade_side,
            )

    offset = 0.002  # 0.2% working limit around mark
    if trade_side == "BUY":
        raw_price = mark * (1 - offset)
        return round(math.floor(raw_price / tick) * tick, 8)
    raw_price = mark * (1 + offset)
    return round(math.ceil(raw_price / tick) * tick, 8)


def enforce_isolated_margin(client: Any, symbol: str) -> Optional[str]:
    """Best-effort set ISOLATED margin mode, then verify against the exchange
    rather than trusting the call succeeded. Returns None if confirmed
    ISOLATED, or a fail-closed rejection reason string otherwise (e.g. an
    existing CROSSED position blocked the change).

    Shared by every order-submission path in this codebase -- originally this
    check lived only in SignalQueueManager.dispatch_queued_signal, which left
    the direct order-placement endpoint (paper_session_routes.py's
    place_binance_testnet_order) able to submit real orders under whatever
    margin mode the exchange already had configured (CROSSED by default) with
    no verification at all. REQUIRED_MARGIN_TYPE is fixed system policy, not
    caller-configurable, by design -- this function takes no margin_type
    argument.
    """
    try:
        client.set_margin_type(symbol, REQUIRED_MARGIN_TYPE)
    except Exception as e:
        logger.warning("Could not set margin type for %s to %s: %s", symbol, REQUIRED_MARGIN_TYPE, e)

    confirmed_margin_type = client.get_symbol_margin_type(symbol)
    if confirmed_margin_type != REQUIRED_MARGIN_TYPE:
        return (
            f"MARGIN_MODE_MISMATCH for {symbol}: required {REQUIRED_MARGIN_TYPE}, "
            f"exchange confirmed {confirmed_margin_type}; order blocked rather than "
            f"executing on the wrong margin mode."
        )
    return None


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

    if clean_producer not in _KNOWN_PRODUCERS:
        return f"producer '{producer}' is not a recognized producer identity and cannot enter the live execution queue"

    # Preserve the exact existing message for idim_ikang (asserted verbatim by
    # test_archive_and_idim_roles_are_separated).
    if clean_producer == "idim_ikang" and not str(source_signal_id or "").strip():
        return "producer 'idim_ikang' must include source_signal_id from the upstream live signal"

    # Generalized rule: any non-scaffs_picker producer must carry provenance.
    if clean_producer != "scaffs_picker" and not str(source_signal_id or "").strip():
        return f"producer '{producer}' must include source_signal_id from its upstream signal"

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
        # Prefer true upstream signal-generation time over queue-insertion
        # time when the producer supplied one; created_at only measures how
        # long a signal has sat in the queue, not how old it actually is.
        origin = s.get("signal_generated_at") or s["created_at"]
        age_sec = max(0.0, (datetime.now(timezone.utc) - origin).total_seconds())
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


# ─── Batch-Independent Absolute Quality Score ──────────────────────────────────

def compute_absolute_quality_score(
    raw_score: float,
    criteria: Dict[str, Any],
    signal_generated_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> float:
    """Score a single signal against FIXED reference anchors, independent of
    whatever else happens to be in the queue.

    rank_signals_topsis answers "how does this compare to today's batch?"
    (batch-relative, can change as unrelated signals arrive/expire). This
    answers "how good is this signal in isolation?" -- the same input always
    yields the same output. Uses the same four weighted criteria as
    rank_signals_topsis (raw_score, freshness, regime_fit, vol_score) so the
    two scores stay conceptually comparable, but ideal-best/ideal-worst are
    fixed constants instead of the batch's max/min:
      - ideal worst raw_score = the absolute admission floor (60.0) -- the
        same floor enqueue_signal already enforces, so "worst admissible" is
        not an arbitrary constant.
      - ideal worst for the other three = 0 (the theoretical floor).
      - ideal best = 100 for all four (their natural 0-100 ceiling).
    """
    now = now or datetime.now(timezone.utc)
    origin = signal_generated_at or now
    age_sec = max(0.0, (now - origin).total_seconds())

    score = float(raw_score)
    freshness_score = max(0.0, 100.0 - age_sec * 0.5)
    regime_fit = float(criteria.get("regime_fit", 75.0))
    vol_score = min(100.0, float(criteria.get("vol_ratio", 1.0)) * 50.0)

    weights = [0.35, 0.25, 0.25, 0.15]
    values = [score, freshness_score, regime_fit, vol_score]
    worst = [_ABSOLUTE_SCORE_FLOOR, 0.0, 0.0, 0.0]
    best = [100.0, 100.0, 100.0, 100.0]

    norm = []
    for v, w, b in zip(values, worst, best):
        span = b - w
        n = (v - w) / span if span > 0 else 1.0
        norm.append(min(1.0, max(0.0, n)))

    d_best = math.sqrt(sum((weights[i] * (norm[i] - 1.0)) ** 2 for i in range(4)))
    d_worst = math.sqrt(sum((weights[i] * norm[i]) ** 2 for i in range(4)))
    total = d_best + d_worst
    return round(d_worst / total, 4) if total > 0 else 0.5


# ─── Queue Operations & Database Persistence ───────────────────────────────────

class SignalQueueManager:
    """Manages signal queuing, quality gating, collision resolution, and execution."""

    def __init__(self, dsn: Optional[str] = None):
        # Resolve through _get_default_dsn(), never raw DATABASE_URL: it already
        # applies the VIBE_PAPER_DATABASE_URL -> DATABASE_URL precedence AND
        # rewrites the host's "/var/run/postgresql" socket DSN, which does not
        # exist inside the container. Reading DATABASE_URL directly here
        # bypassed that rewrite and made every connect fail in Docker.
        self.dsn = dsn or _get_default_dsn()

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
        signal_timestamp: Optional[str] = None,
        conn: Optional[Any] = None,
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
            status = (
                "REJECTED_UNKNOWN_PRODUCER"
                if "not a recognized producer identity" in role_error
                else "REJECTED_SOURCE_ROLE"
            )
            return {
                "ok": False,
                "status": status,
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

        signal_generated_dt = _parse_signal_timestamp(signal_timestamp)
        now_dt = datetime.now(timezone.utc)
        absolute_quality_score = compute_absolute_quality_score(raw_score, crit, signal_generated_dt, now_dt)

        # 3. Insert into PostgreSQL (reuse external connection when given)
        con = conn or psycopg.connect(self.dsn)
        should_close = conn is None
        try:
            try:
                with con.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO paper_trading.signal_queue (
                            id, source_signal_id, producer, symbol, side, timeframe,
                            raw_score, criteria_vector, target_strategy, status, ttl_seconds,
                            signal_generated_at, absolute_quality_score
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s::jsonb, %s, 'PENDING', %s,
                            %s, %s
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
                            signal_generated_dt,
                            absolute_quality_score,
                        ),
                    )
                    res = cur.fetchone()
                con.commit()
            except psycopg_errors.UniqueViolation:
                # Must roll back explicitly: idim_feed_bridge shares one
                # connection across its whole ingestion batch, and a failed
                # transaction left un-rolled-back would poison every
                # subsequent insert in that batch, not just this duplicate.
                con.rollback()
                return {
                    "ok": False,
                    "status": "REJECTED_DUPLICATE_SIGNAL",
                    "reason": f"An active queue entry already exists for source_signal_id={source_signal_id!r}.",
                }
        finally:
            if should_close:
                con.close()

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
            "absolute_quality_score": absolute_quality_score,
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

            # A crash between claim_signal succeeding and any terminal write
            # would otherwise strand a row in CLAIMED forever -- reap it too.
            cur.execute(
                """
                UPDATE paper_trading.signal_queue
                SET status = 'EXPIRED',
                    rejection_reason = 'Claim held past claim timeout without a terminal outcome'
                WHERE status = 'CLAIMED'
                  AND NOW() > (claimed_at + INTERVAL '120 seconds');
                """
            )
            expired_count += cur.rowcount
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
                       raw_score, criteria_vector, target_strategy, created_at, ttl_seconds,
                       signal_generated_at, absolute_quality_score
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
                    "signal_generated_at": r[11],
                    "absolute_quality_score": float(r[12]) if r[12] is not None else None,
                })

        # Multi-criteria ranking
        ranked = rank_signals_topsis(signals)
        return ranked

    def check_position_collision(self, symbol: str, incoming_side: str) -> Tuple[bool, str, str]:
        """Verify if incoming signal collides with current open inventory.

        Returns (can_execute, reason, state) where state is one of
        FLAT / SAME_SIDE / OPPOSING / UNKNOWN. UNKNOWN (the position-risk API
        call failed) is NOT treated as safe -- an unverifiable inventory state
        fails CLOSED, not open. "No position exists" and "we couldn't
        determine whether a position exists" are different facts; only the
        former is safe to execute on.
        """
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client, BinanceFuturesConfig

        client = get_binance_futures_client(BinanceFuturesConfig.from_env())
        try:
            positions = client.get_positions(symbol=symbol)
        except Exception as e:
            logger.warning("Could not query live position risk for collision check (%s): %s", symbol, e)
            return (
                False,
                f"Position-risk check failed ({e}); dispatch blocked until inventory can be verified.",
                "UNKNOWN",
            )

        for p in positions:
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0.0:
                current_side = "BUY" if amt > 0 else "SELL"
                if current_side != incoming_side.upper():
                    return (
                        False,
                        f"Opposing position open ({amt} {symbol} {current_side}). Signal {incoming_side} blocked to prevent unmanaged flip-flop.",
                        "OPPOSING",
                    )
                return True, f"Scale-in permissible on existing {current_side} position.", "SAME_SIDE"

        return True, "Flat inventory — execution clear.", "FLAT"

    def claim_signal(self, queue_id: str) -> Dict[str, Any]:
        """Atomically transition PENDING -> CLAIMED and mint an HMAC claim receipt.

        This is the ONLY place a queued signal moves out of PENDING, and it
        must run before any exchange interaction. A plain
        "SELECT status then UPDATE later" (the previous implementation) lets
        two concurrent dispatch callers both observe PENDING and both proceed
        to submit an order for the same queue_id; the conditional UPDATE here
        (compare-and-swap on status='PENDING') means only one caller's write
        can succeed. Every subsequent terminal write for this queue_id must
        include `AND status='CLAIMED' AND claim_token=%s` in its WHERE clause
        so only the process holding the winning claim can record an outcome.
        """
        claimed_at = datetime.now(timezone.utc)
        token = _make_claim_token(queue_id, claimed_at)
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE paper_trading.signal_queue
                SET status = 'CLAIMED', claimed_at = %s, claim_token = %s
                WHERE id = %s AND status = 'PENDING'
                RETURNING symbol, side, topsis_score, raw_score, target_strategy,
                          created_at, ttl_seconds, criteria_vector,
                          signal_generated_at, absolute_quality_score;
                """,
                (claimed_at, token, queue_id),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT status FROM paper_trading.signal_queue WHERE id = %s;", (queue_id,))
                existing = cur.fetchone()
                conn.commit()
                if existing is None:
                    return {"ok": False, "status": "NOT_FOUND", "reason": f"Queued signal {queue_id} not found."}
                return {
                    "ok": False,
                    "status": "ALREADY_CLAIMED",
                    "current_status": existing[0],
                    "reason": f"Signal {queue_id} is not PENDING (current status '{existing[0]}'); "
                              "it is already claimed, dispatched, or expired.",
                }
            conn.commit()

        (symbol, side, topsis_score, raw_score, target_strategy, created_at,
         ttl_seconds, criteria_raw, signal_generated_at, absolute_quality_score) = row
        criteria = criteria_raw if isinstance(criteria_raw, dict) else json.loads(criteria_raw or "{}")
        return {
            "ok": True,
            "claim_token": token,
            "claimed_at": claimed_at,
            "symbol": symbol,
            "side": side,
            "topsis_score": topsis_score,
            "raw_score": raw_score,
            "target_strategy": target_strategy,
            "created_at": created_at,
            "ttl_seconds": ttl_seconds,
            "criteria_vector": criteria,
            "signal_generated_at": signal_generated_at,
            "absolute_quality_score": absolute_quality_score,
        }

    def _target_leverage(self, target_strategy: str) -> int:
        if target_strategy.endswith("_10x"):
            return 10
        if target_strategy.endswith("_5x"):
            return 5
        if target_strategy.startswith("rebalance"):
            return 5
        return 1

    def _reconcile_order(self, client: Any, symbol: str, queue_id: str, order_id: str) -> dict[str, Any]:
        """Query the exchange for the latest order state and fills."""
        fill_summary: dict[str, Any] = {"order_id": order_id, "status": "SUBMITTED"}
        try:
            order = client.get_order(symbol=symbol, client_order_id=queue_id[:32])
            exchange_status = (order.get("status") or "").upper()
            fill_summary["status"] = exchange_status if exchange_status in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"} else "SUBMITTED"
            fill_summary["executed_qty"] = float(order.get("executedQty", 0) or 0)
            fill_summary["cum_quote"] = float(order.get("cumQuote", 0) or 0)
            fill_summary["avg_price"] = float(order.get("avgPrice", 0) or order.get("price", 0) or 0)
            if order_id:
                try:
                    trades = client.get_order_trades(symbol=symbol, order_id=int(order_id))
                    if trades:
                        total_comm = sum(float(t.get("commission", 0) or 0) for t in trades)
                        total_realized = sum(float(t.get("realizedPnl", 0) or 0) for t in trades)
                        fill_summary["commission"] = total_comm
                        fill_summary["realized_pnl"] = total_realized
                        fill_summary["trades"] = trades
                except Exception as e:
                    logger.warning("Could not fetch order trades for %s: %s", order_id, e)
        except Exception as e:
            logger.warning("Could not reconcile order %s on exchange: %s", order_id, e)
        return fill_summary

    def _quantity_from_risk_pct(
        self,
        risk_pct: float,
        entry_price: float,
        stop_loss: float,
        risk_base_equity_usdt: float,
        precision: int,
        fee_rate: float = _DEFAULT_ROUND_TRIP_FEE_RATE,
        slippage_pct: float = _DEFAULT_STOP_SLIPPAGE_PCT,
    ) -> float:
        """Position size from risk budget and stop distance -- an optional
        ALTERNATIVE to notional_usd sizing, never a replacement. Only invoked
        when the caller supplies risk_pct AND the signal carries a
        stop_loss; stop_loss stays optional everywhere else.

        risk_base_equity_usdt should be total wallet balance (equity), not
        available/free margin -- opening one isolated position reserves
        margin and shrinks available balance, which must not itself change
        what risk_pct nominally means for the next trade. Capital
        sufficiency (can we actually afford the margin right now) is a
        separate check, already enforced by the Step 4 risk gate's
        INSUFFICIENT_AVAILABLE_BALANCE check against available_balance_usdt.

        The stop distance alone understates real risk: a stop can fill worse
        than its trigger (slippage), and both entry and exit pay fees. Both
        are folded into the denominator as a per-unit cost buffer so the
        realized loss on a worst-case stop-out stays close to the intended
        risk budget, not silently larger than it.

        Rounds the resulting quantity DOWN (floor) to the exchange step size,
        not up -- rounding up would let actual risk exceed risk_pct.
        """
        if risk_pct <= 0:
            raise ValueError(f"risk_pct ({risk_pct}) must be > 0.")
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            raise ValueError(
                f"stop_loss ({stop_loss}) is not distinct from entry_price ({entry_price}); "
                "cannot size a position by risk with zero stop distance."
            )
        cost_buffer_per_unit = entry_price * (fee_rate + slippage_pct)
        effective_risk_distance = stop_distance + cost_buffer_per_unit
        risk_budget = risk_base_equity_usdt * risk_pct
        raw_qty = risk_budget / effective_risk_distance
        step = 10 ** -precision
        return round(math.floor(raw_qty / step) * step, precision)

    def dispatch_queued_signal(
        self,
        queue_id: str,
        quantity: Optional[float] = None,
        notional_usd: float = 100.0,
        risk_pct: Optional[float] = None,
        entry_ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch a ranked queued signal through the risk gate to Binance."""
        from src.trading.connectors.binance.binance_testnet_executor import BinanceTestnetExecutor
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client
        from src.trading.trade_intent import TradeIntent

        # 1. Atomically claim the signal -- the only place it leaves PENDING.
        # No exchange interaction happens before this succeeds, so a second
        # concurrent caller for the same queue_id gets a clean rejection here
        # instead of racing past a plain status check.
        claim = self.claim_signal(queue_id)
        if not claim["ok"]:
            result: Dict[str, Any] = {
                "ok": False,
                "status": claim["status"],
                "queue_id": queue_id,
                "reason": claim.get("reason"),
            }
            if "current_status" in claim:
                result["current_status"] = claim["current_status"]
            return result

        symbol = claim["symbol"]
        side = claim["side"]
        topsis_score = claim["topsis_score"]
        raw_score = claim["raw_score"]
        strategy = claim["target_strategy"]
        created_at = claim["created_at"]
        ttl = claim["ttl_seconds"]
        criteria = claim["criteria_vector"]
        signal_generated_at = claim["signal_generated_at"]
        claim_token = claim["claim_token"]
        clean_sym = symbol.upper()
        side_norm = side.upper()
        trade_side = "BUY" if side_norm in {"LONG", "BUY"} else "SELL"

        def _write_terminal(new_status: str, reason: str) -> None:
            """Write a terminal outcome, gated on still holding the claim."""
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET status = %s,
                        rejection_reason = %s,
                        completed_at = NOW()
                    WHERE id = %s AND status = 'CLAIMED' AND claim_token = %s;
                    """,
                    (new_status, reason, queue_id, claim_token),
                )
                if cur.rowcount == 0:
                    logger.error(
                        "Claim token mismatch writing terminal status %s for signal [%s]; "
                        "row was not updated (should not happen given the CAS in claim_signal).",
                        new_status, queue_id,
                    )
                conn.commit()

        # 2. Position Collision Check
        can_exec, collision_note, collision_state = self.check_position_collision(clean_sym, trade_side)
        if not can_exec:
            new_status = "COLLISION_UNKNOWN" if collision_state == "UNKNOWN" else "COLLISION_BLOCKED"
            _write_terminal(new_status, collision_note)
            return {"ok": False, "status": new_status, "queue_id": queue_id, "reason": collision_note}

        # 2b. Risk-fraction ceiling: enforced regardless of what the caller/
        # signal requests -- checked before any exchange interaction, since
        # it's a pure input-validation failure, not a market/exchange one.
        _effective_risk_pct_check = risk_pct if risk_pct is not None else criteria.get("risk_pct")
        if _effective_risk_pct_check is not None:
            _risk_pct_val = float(_effective_risk_pct_check)
            if _risk_pct_val <= 0 or _risk_pct_val > _MAX_RISK_PCT_PER_TRADE:
                reason = (
                    f"RISK_PCT_EXCEEDS_MAX: requested {_risk_pct_val:.4f} must be in "
                    f"(0, {_MAX_RISK_PCT_PER_TRADE:.4f}] -- the ceiling is frozen policy, "
                    f"not caller-controlled."
                )
                logger.warning(reason)
                _write_terminal("RISK_PCT_EXCEEDS_MAX", reason)
                return {"ok": False, "status": "RISK_PCT_EXCEEDS_MAX", "queue_id": queue_id, "reason": reason}

        # 3. Risk/execution environment defaults tuned for $100 signal notional.
        os.environ.setdefault("MAX_TRADE_NOTIONAL_USDT", "1000")
        os.environ.setdefault("MAX_POSITION_NOTIONAL_USDT", "10000")
        os.environ.setdefault("MAX_LEVERAGE", "10")
        os.environ.setdefault("MIN_AVAILABLE_BALANCE_USDT", "1")
        os.environ.setdefault("MAX_OPEN_POSITIONS", "100")
        os.environ.setdefault("TRADE_COOLDOWN_SECONDS", "0")
        os.environ.setdefault("MAX_MARKET_DATA_AGE_SECONDS", "1000")
        if (os.getenv("TRADING_ENV") or "").strip().lower() == "binance_testnet":
            os.environ.setdefault("ALLOWED_SYMBOLS", "*")
        else:
            os.environ.setdefault("ALLOWED_SYMBOLS", "BTC-USDT,ETH-USDT,SOL-USDT,BNB-USDT")

        # 4. Compute price and requested leverage
        client = get_binance_futures_client()
        ticker_px = client.get_ticker_price(clean_sym)
        if ticker_px <= 0:
            ticker_px = 1.0

        requested_leverage = int(criteria.get("requested_leverage") or self._target_leverage(strategy))

        # 5. Margin mode: every dispatch must run on ISOLATED margin -- fixed
        # system policy, not signal-configurable. CROSSED puts the whole
        # futures wallet behind a single position instead of just that
        # position's own margin.
        margin_reason = enforce_isolated_margin(client, clean_sym)
        if margin_reason:
            logger.warning(margin_reason)
            _write_terminal("MARGIN_MODE_MISMATCH_BLOCKED", margin_reason)
            return {"ok": False, "status": "MARGIN_MODE_MISMATCH_BLOCKED", "queue_id": queue_id, "reason": margin_reason}

        # 6. Enforce confirmed leverage invariant: attempt the target, and
        # abort rather than silently continuing at a different leverage than
        # the strategy authorized if the exchange reports a mismatch.
        try:
            client.set_leverage(clean_sym, requested_leverage)
        except Exception as lev_err:
            logger.warning("Could not set leverage for %s to %sx: %s", clean_sym, requested_leverage, lev_err)

        confirmed_leverage = client.get_symbol_leverage(clean_sym)
        if confirmed_leverage != requested_leverage:
            reason = (
                f"LEVERAGE_MISMATCH for {clean_sym}: wanted {requested_leverage}x, "
                f"exchange confirmed {confirmed_leverage}x; dispatch aborted rather than "
                f"silently executing at a different leverage than the strategy authorized."
            )
            logger.warning(reason)
            _write_terminal("LEVERAGE_MISMATCH_BLOCKED", reason)
            return {"ok": False, "status": "LEVERAGE_MISMATCH_BLOCKED", "queue_id": queue_id, "reason": reason}

        # 6. Every entry is a LIMIT order now -- never MARKET. Resolve the
        # entry price before sizing: risk-based sizing needs it to compute
        # stop distance.
        order_type = "LIMIT"
        tick = client.get_price_tick_size(clean_sym)
        limit_price = _resolve_limit_price(trade_side, ticker_px, criteria.get("entry"), tick)

        # 7. Calculate quantity (rounded up to symbol precision) and verify
        # actual notional. risk_pct is an OPTIONAL ALTERNATIVE to
        # notional_usd sizing -- only used when both a risk_pct and a
        # stop_loss are present; stop_loss stays optional everywhere else.
        sl_for_sizing = criteria.get("stop_loss")
        effective_risk_pct = risk_pct if risk_pct is not None else criteria.get("risk_pct")
        sizing_mode = "notional_usd"
        if quantity is None:
            precision = client.get_quantity_precision(clean_sym)
            if effective_risk_pct is not None and sl_for_sizing is not None:
                from src.trading.risk.binance_state_adapter import BinanceTestnetStateProvider

                snapshot = BinanceTestnetStateProvider(client=client).account_snapshot()
                # Risk-base equity, NOT available/free margin: opening one
                # isolated position reserves margin and shrinks available
                # balance, which must not itself change what risk_pct means
                # for the next trade. Capital sufficiency is still enforced
                # separately by the Step 4 gate's INSUFFICIENT_AVAILABLE_BALANCE
                # check against available_balance_usdt. Fall back to available
                # balance only if wallet balance genuinely couldn't be read.
                risk_base_equity = float(snapshot.total_wallet_balance_usdt or snapshot.available_balance_usdt)
                quantity = self._quantity_from_risk_pct(
                    float(effective_risk_pct), limit_price, float(sl_for_sizing), risk_base_equity, precision,
                )
                sizing_mode = "risk_pct"
            else:
                step = 10 ** -precision
                raw_qty = notional_usd / ticker_px
                quantity = math.ceil(raw_qty / step) * step
                quantity = round(quantity, precision)

        if sizing_mode == "notional_usd":
            actual_notional = quantity * ticker_px
            if actual_notional < 0.9 * notional_usd or actual_notional > 1.1 * notional_usd:
                sizing = (
                    f"NOTIONAL_STEP_TOO_COARSE: target ${notional_usd} maps to ${actual_notional:.2f} "
                    f"(quantity {quantity} @ {ticker_px:.2f})"
                )
                _write_terminal("EXECUTION_FAILED", sizing)
                return {"ok": False, "status": "EXECUTION_FAILED", "queue_id": queue_id, "reason": sizing}
        # risk_pct mode skips the notional-band check -- the target is a risk
        # budget, not a notional; the Step 4 risk gate (MAX_TRADE_NOTIONAL_USDT
        # etc, run inside executor.submit() below) still catches an
        # oversized risk_pct-derived quantity.

        effective_entry_ttl = int(
            entry_ttl_seconds if entry_ttl_seconds is not None
            else criteria.get("entry_ttl_seconds", _DEFAULT_ENTRY_TTL_SECONDS)
        )

        # 8. Build exchange-agnostic TradeIntent.
        # Preserve the signal's true origin time for provenance/audit -- do
        # NOT stamp it with dispatch-time "now", which would make every
        # dispatched intent look like it originated at the moment it was
        # executed rather than when it was actually generated upstream.
        # dispatch-time "now" is still correct for the market snapshot below,
        # since that legitimately describes when we checked the market, not
        # when the signal originated.
        signal_origin_dt = signal_generated_at or created_at
        signal_origin_ts = signal_origin_dt.isoformat()
        dispatch_now_ts = datetime.now(timezone.utc).isoformat()
        sl = criteria.get("stop_loss")
        tp = criteria.get("take_profit")
        range_meta = {
            "entry": criteria.get("entry"),
            "stop_loss": sl,
            "take_profit": tp,
            "regime": criteria.get("regime"),
        }
        intent = TradeIntent(
            intent_id=queue_id,
            strategy_id=strategy,
            symbol=clean_sym,
            side=trade_side,
            quantity=quantity,
            notional=notional_usd,
            order_type=order_type,
            limit_price=limit_price,
            stop_loss=float(sl) if sl is not None else None,
            take_profit=float(tp) if tp is not None else None,
            range_metadata=range_meta,
            reduce_only=False,
            reason=f"signal {queue_id}",
            signal_timestamp=signal_origin_ts,
            market_snapshot={
                "price": ticker_px,
                "leverage": confirmed_leverage,
                "timestamp": dispatch_now_ts,
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
                order_id = result.exchange_order_id or ""
                client_order_id = queue_id[:32]
                fill_summary = self._reconcile_order(client, clean_sym, queue_id, order_id)
                criteria["execution"] = fill_summary
                filled_qty = float(fill_summary.get("executed_qty", 0.0) or 0.0)

                if result.status == "FILLED":
                    # Immediate-fill fast path (the existing _submit_real
                    # confirm-loop already saw a fill, and either attached
                    # protection successfully or none was needed): the state
                    # machine's job is done without waiting for the poller.
                    final_status = "PROTECTED"
                    is_terminal = True
                else:
                    # Still resting -- NOT a final outcome anymore.
                    # reconcile_pending_entries() (the async poller) is the
                    # only thing that revisits this row from here: on
                    # confirmed fill it attaches protection sized to whatever
                    # actually filled; on entry_ttl_seconds elapsed with zero
                    # fill it cancels the order.
                    final_status = "PARTIALLY_FILLED" if filled_qty > 0 else "DISPATCHED"
                    is_terminal = False

                with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE paper_trading.signal_queue
                        SET status = %s,
                            execution_order_id = %s,
                            execution_client_order_id = %s,
                            topsis_score = %s,
                            criteria_vector = %s,
                            requested_quantity = %s,
                            filled_quantity = %s,
                            entry_ttl_seconds = %s,
                            dispatched_at = NOW(),
                            completed_at = CASE WHEN %s THEN NOW() ELSE NULL END
                        WHERE id = %s AND status = 'CLAIMED' AND claim_token = %s;
                        """,
                        (final_status, order_id, client_order_id, topsis_score, Json(criteria),
                         quantity, filled_qty, effective_entry_ttl, is_terminal, queue_id, claim_token),
                    )
                    if cur.rowcount == 0:
                        logger.error(
                            "Claim token mismatch writing %s for signal [%s]; "
                            "order %s was placed on the exchange but the queue row was not updated.",
                            final_status, queue_id, order_id,
                        )
                    conn.commit()

                logger.info("Signal [%s] -> %s (exchange status %s, order %s)", queue_id, final_status, result.status, order_id)
                return {
                    "ok": True,
                    "status": final_status,
                    "queue_id": queue_id,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "fill_summary": fill_summary,
                    "execution_result": result.to_dict(),
                }

            if result.status == "PROTECTION_FAILED":
                order_id = result.exchange_order_id or ""
                client_order_id = queue_id[:32]
                fill_summary = self._reconcile_order(client, clean_sym, queue_id, order_id)
                criteria["execution"] = fill_summary
                criteria["protective_orders"] = result.to_dict().get("protective_orders", [])
                criteria["protection_status"] = result.to_dict().get("protection_status")
                filled_qty = float(fill_summary.get("executed_qty", 0.0) or 0.0)
                with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE paper_trading.signal_queue
                        SET status = 'PROTECTION_FAILED',
                            execution_order_id = %s,
                            execution_client_order_id = %s,
                            topsis_score = %s,
                            criteria_vector = %s,
                            requested_quantity = %s,
                            filled_quantity = %s,
                            entry_ttl_seconds = %s,
                            dispatched_at = NOW()
                        WHERE id = %s AND status = 'CLAIMED' AND claim_token = %s;
                        """,
                        (order_id, client_order_id, topsis_score, Json(criteria),
                         quantity, filled_qty, effective_entry_ttl, queue_id, claim_token),
                    )
                    if cur.rowcount == 0:
                        logger.error(
                            "Claim token mismatch writing PROTECTION_FAILED for signal [%s]; "
                            "entry order %s filled but the queue row was not updated.",
                            queue_id, order_id,
                        )
                    conn.commit()
                # No completed_at: PROTECTION_FAILED is retryable, not terminal
                # -- reconcile_pending_entries() will retry attaching
                # protection on its next pass rather than abandoning the
                # position unprotected.
                logger.warning("Signal [%s] entry filled but protective orders failed: %s", queue_id, result.error)
                return {
                    "ok": False,
                    "status": "PROTECTION_FAILED",
                    "queue_id": queue_id,
                    "order_id": order_id,
                    "reason": result.error,
                    "fill_summary": fill_summary,
                    "execution_result": result.to_dict(),
                }

            # Risk or execution rejected/failed
            failure_reason = str(result.error or result.status)
            _write_terminal("EXECUTION_FAILED", failure_reason)

            logger.warning("Signal [%s] failed at risk/execution: %s", queue_id, failure_reason)
            return {
                "ok": False,
                "status": "EXECUTION_FAILED",
                "queue_id": queue_id,
                "reason": failure_reason,
                "execution_result": result.to_dict(),
            }
        except Exception as exc:
            _write_terminal("EXECUTION_FAILED", str(exc))
            raise

    def reconcile_pending_entries(
        self, limit: int = 50, queue_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Poll every resting LIMIT entry for fill/TTL state.

        This is the single place that closes the gap left by
        BinanceTestnetExecutor._submit_real's ~1-second fill-confirm window:
        nothing else in this codebase ever revisits an order placed by
        dispatch_queued_signal after the original call returns. Meant to be
        called on a recurring interval (see start_all_services.py).

        On first confirmed fill (full or partial), attaches protection sized
        to whatever is actually open -- closePosition orders don't need an
        exact quantity, so a partial fill is protected exactly as correctly
        as a full one. On TTL elapsed with zero fill, cancels the resting
        order rather than letting a stale entry fill unexpectedly later.

        Known, accepted gap: once a row reaches PROTECTED, a lingering
        unfilled remainder of a partial fill is no longer tracked here (the
        WHERE clause below only selects DISPATCHED/PARTIALLY_FILLED/
        PROTECTION_FAILED) -- it either fills later (harmlessly, still
        covered by the same closePosition protective orders) or rests
        indefinitely. Not solved in this pass.

        `queue_ids`, when given, scopes the sweep to exactly those rows
        instead of every resting entry in the table -- used by tests so they
        don't touch unrelated historical rows in a shared dev database; the
        production caller (start_all_services.py) always omits it.
        """
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client
        from src.trading.connectors.binance.binance_testnet_executor import attach_protective_orders

        client = get_binance_futures_client()
        processed: List[Dict[str, Any]] = []

        query = """
            SELECT id, symbol, side, execution_order_id, criteria_vector,
                   requested_quantity, filled_quantity, dispatched_at,
                   entry_ttl_seconds, status
            FROM paper_trading.signal_queue
            WHERE status = ANY(%s) AND execution_order_id IS NOT NULL
        """
        params: List[Any] = [list(_RESTING_ENTRY_STATUSES)]
        if queue_ids:
            query += " AND id = ANY(%s::uuid[])"
            params.append(list(queue_ids))
        query += " ORDER BY dispatched_at ASC LIMIT %s;"
        params.append(limit)

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        for row in rows:
            (queue_id, symbol, side, order_id, criteria_raw, requested_qty,
             prior_filled_qty, dispatched_at, ttl, current_status) = row
            criteria = criteria_raw if isinstance(criteria_raw, dict) else json.loads(criteria_raw or "{}")
            clean_sym = symbol.upper()
            queue_id_str = str(queue_id)
            # Normalize to BUY/SELL: signal_queue.side preserves whatever the
            # caller originally supplied (LONG/SHORT/BUY/SELL), but exchange
            # calls and live_fills.side (CHECK side IN ('BUY','SELL')) need
            # the normalized form.
            trade_side = "BUY" if str(side).upper() in ("LONG", "BUY") else "SELL"

            outcome = self._reconcile_order(client, clean_sym, queue_id_str, order_id)
            exch_status = outcome.get("status")
            filled_qty = float(outcome.get("executed_qty", 0.0) or 0.0)

            if filled_qty > 0 and current_status in ("DISPATCHED", "PARTIALLY_FILLED", "PROTECTION_FAILED"):
                # PROTECTION_FAILED is included here (not just DISPATCHED/
                # PARTIALLY_FILLED) so a prior failed protection attempt
                # actually gets retried -- it's in _RESTING_ENTRY_STATUSES
                # (queried above) precisely so this retry can happen.
                self._record_live_fills(queue_id, clean_sym, trade_side, order_id, outcome.get("trades") or [])
                sl = criteria.get("stop_loss")
                tp = criteria.get("take_profit")
                mark = outcome.get("avg_price") or client.get_ticker_price(clean_sym)
                protective_orders, protection_status, protection_error = attach_protective_orders(
                    client=client,
                    symbol=clean_sym,
                    side=trade_side,
                    stop_loss=float(sl) if sl is not None else None,
                    take_profit=float(tp) if tp is not None else None,
                    mark_price=float(mark),
                    intent_id=queue_id_str,
                )
                criteria["execution"] = outcome
                criteria["protective_orders"] = protective_orders
                new_status = "PROTECTED" if protection_status in ("PROTECTED", "NO_BOUNDARIES") else "PROTECTION_FAILED"
                self._write_reconcile_outcome(
                    queue_id_str, new_status, filled_qty, criteria,
                    reason=protection_error, terminal=(new_status == "PROTECTED"),
                )
                processed.append({"queue_id": queue_id_str, "outcome": new_status})
                continue

            if exch_status in ("CANCELED", "EXPIRED", "REJECTED"):
                self._write_reconcile_outcome(
                    queue_id_str, "ENTRY_CANCELLED_TTL", filled_qty, criteria,
                    reason=f"order {exch_status.lower()} on exchange", terminal=True,
                )
                processed.append({"queue_id": queue_id_str, "outcome": "ENTRY_CANCELLED_TTL"})
                continue

            age_seconds = (datetime.now(timezone.utc) - dispatched_at).total_seconds()
            if age_seconds > (ttl or _DEFAULT_ENTRY_TTL_SECONDS):
                try:
                    client.cancel_order(clean_sym, order_id=int(order_id))
                except Exception as exc:
                    logger.warning("TTL cancel failed for [%s] order %s: %s", queue_id_str, order_id, exc)
                    continue  # retry next tick rather than mark cancelled on an unconfirmed cancel
                self._write_reconcile_outcome(
                    queue_id_str, "ENTRY_CANCELLED_TTL", filled_qty, criteria,
                    reason="TTL expired before fill; entry cancelled", terminal=True,
                )
                processed.append({"queue_id": queue_id_str, "outcome": "ENTRY_CANCELLED_TTL"})
                continue

            # Still resting, no new fill, TTL not yet reached: nothing to do this tick.

        return {"ok": True, "checked": len(rows), "processed": processed}

    def _record_live_fills(
        self,
        queue_id: Any,
        symbol: str,
        side: str,
        order_id: Optional[str],
        trades: List[Dict[str, Any]],
    ) -> None:
        """Record authoritative live-testnet fills into paper_trading.live_fills.

        This is what makes PositionReconciler able to see real live positions
        at all -- position/provenance.py::aggregate_fills() reads this table
        alongside paper_trading.fills. Idempotent via ON CONFLICT DO NOTHING
        (exchange_order_id, exchange_fill_id) since the poller may observe
        the same userTrades rows again on a later tick.
        """
        if not trades or not order_id:
            return
        rows = []
        for t in trades:
            try:
                fill_id = str(t.get("id")) if t.get("id") is not None else None
                qty = float(t.get("qty", 0) or 0)
                price = float(t.get("price", 0) or 0)
                fee = float(t.get("commission", 0) or 0)
                time_ms = int(t.get("time", 0) or 0)
            except (TypeError, ValueError):
                continue
            if qty <= 0 or price <= 0:
                continue
            filled_at = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc) if time_ms > 0 else datetime.now(timezone.utc)
            rows.append((queue_id, fill_id, str(order_id), symbol, side.upper(), qty, price, fee, filled_at))
        if not rows:
            return
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO paper_trading.live_fills (
                        queue_id, exchange_fill_id, exchange_order_id, symbol, side,
                        quantity, price, fee, filled_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (exchange_order_id, exchange_fill_id) DO NOTHING;
                    """,
                    row,
                )
            conn.commit()

    def _write_reconcile_outcome(
        self,
        queue_id: str,
        status: str,
        filled_quantity: float,
        criteria: Dict[str, Any],
        reason: Optional[str],
        terminal: bool,
    ) -> None:
        """Write an outcome discovered by reconcile_pending_entries(). Gated
        on the status this poller itself selected (an optimistic check, not
        the claim-token CAS): the claim already succeeded at dispatch time,
        and this poller is the only writer of these particular transitions.
        """
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE paper_trading.signal_queue
                SET status = %s,
                    filled_quantity = %s,
                    criteria_vector = %s,
                    rejection_reason = %s,
                    completed_at = CASE WHEN %s THEN NOW() ELSE completed_at END
                WHERE id = %s AND status = ANY(%s);
                """,
                (status, filled_quantity, Json(criteria), reason, terminal,
                 queue_id, list(_RESTING_ENTRY_STATUSES)),
            )
            conn.commit()
