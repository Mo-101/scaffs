"""Binance USD-M Futures Testnet execution adapter.

Translates exchange-agnostic ``TradeIntent`` objects into calls to
``futures_sdk.place_order``.  ``EXECUTION_ENABLED`` defaults to false so that
strategy cycles can be wired and audited without autonomously submitting real
orders.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from src.trading.trade_intent import ExecutionResult, TradeIntent
from src.trading.connectors.binance.futures_sdk import (
    BinanceFuturesClient,
    get_binance_futures_client,
)

logger = logging.getLogger(__name__)

EXECUTION_ENABLED_ENV = "EXECUTION_ENABLED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_binance_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "")


def _persist_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _persist_intent(session_dir: Optional[Path], record: dict[str, Any]) -> None:
    if session_dir is None:
        return
    _persist_jsonl(session_dir / "intents.jsonl", record)


def _persist_result(session_dir: Optional[Path], result: ExecutionResult) -> None:
    if session_dir is None:
        return
    record = {**result.to_dict(), "recorded_at": _now_iso()}
    _persist_jsonl(session_dir / "executions.jsonl", record)


def _to_pre_trade_intent(intent: TradeIntent):
    """Convert the strategy-level TradeIntent to the Step 4 risk contract shape."""
    from src.trading.risk.pre_trade import MarketSnapshot, TradeIntent as PreTradeIntent

    symbol = _format_binance_symbol(intent.symbol)
    market = intent.market_snapshot or {}
    price = Decimal(str(market.get("price", "0")))
    if price <= 0:
        price = Decimal(str(market.get("mark_price", "0")))

    ts = market.get("timestamp") or intent.signal_timestamp or _now_iso()
    try:
        epoch = int(datetime.fromisoformat(ts).timestamp())
    except (ValueError, TypeError):
        epoch = int(time.time())

    if intent.quantity is not None and intent.quantity > 0:
        quantity = Decimal(str(intent.quantity))
    elif intent.notional is not None and intent.notional > 0 and price > 0:
        quantity = Decimal(str(intent.notional)) / price
    else:
        quantity = Decimal("0")

    requested_leverage = Decimal(str(market.get("leverage", "1")))
    if requested_leverage <= 0:
        requested_leverage = Decimal("1")

    return PreTradeIntent(
        intent_id=intent.intent_id,
        symbol=symbol,
        side=intent.side,
        order_type=intent.order_type,
        quantity=quantity,
        reduce_only=intent.reduce_only,
        requested_leverage=requested_leverage,
        market_snapshot=MarketSnapshot(
            symbol=symbol,
            mark_price=price,
            timestamp_epoch=epoch,
            status="OK",
        ),
        stop_loss=Decimal(str(intent.stop_loss)) if intent.stop_loss is not None else None,
        take_profit=Decimal(str(intent.take_profit)) if intent.take_profit is not None else None,
        range_metadata=intent.range_metadata,
    )


def _round_to_tick(value: float, tick: float) -> float:
    return round(value / tick) * tick


def _validate_tp_sl(side: str, mark: float, sl: float | None, tp: float | None) -> tuple[float | None, float | None, str]:
    """Return (sl, tp, status). Drop any boundary that is on the wrong side of mark."""
    if side.upper() in ("BUY", "LONG"):
        valid_sl = sl if sl is not None and sl < mark else None
        valid_tp = tp if tp is not None and tp > mark else None
        return valid_sl, valid_tp, "VALID"
    # SELL/SHORT
    valid_sl = sl if sl is not None and sl > mark else None
    valid_tp = tp if tp is not None and tp < mark else None
    return valid_sl, valid_tp, "VALID"


def attach_protective_orders(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    stop_loss: float | None,
    take_profit: float | None,
    mark_price: float,
    intent_id: str,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Attach STOP_MARKET (SL) / TAKE_PROFIT_MARKET (TP) closePosition orders.

    Shared by the immediate-fill path (BinanceTestnetExecutor._submit_real,
    via its thin wrapper) and SignalQueueManager.reconcile_pending_entries
    (the async poller that revisits a resting LIMIT order after the original
    dispatch call already returned). closePosition orders don't take a
    quantity -- Binance closes whatever is actually open -- so this is
    correct whether the fill was full or partial.

    Missing boundaries are synthesized from mark price, so both are normally
    requested even for grid/rebalance-style signals that carry no per-trade
    stop concept.

    Returns (orders, status, error), where status reflects the exchange's
    state after the attempt rather than the outcome of the placement calls:
      - "PROTECTED" if every requested boundary is resting on the exchange,
        including when this call's own placement was rejected as a duplicate
        because the reconciler had already attached it.
      - "PROTECTION_FAILED" if a requested boundary is absent, or if the
        exchange could not be queried to confirm either way (fail closed).
    ``orders`` is the set of closePosition orders actually observed on the
    exchange, falling back to whatever this call placed if none were read.
    """
    from decimal import Decimal
    from src.trading.protection_math import protection_levels

    tick = client.get_price_tick_size(symbol)
    econ_side = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"

    # Synthesize missing boundaries if either SL or TP is absent
    if stop_loss is None or take_profit is None:
        synth = protection_levels(
            entry=Decimal(str(mark_price)),
            side=econ_side,
            tick_size=Decimal(str(tick)),
        )
        if stop_loss is None:
            stop_loss = float(synth.stop_loss)
        if take_profit is None:
            take_profit = float(synth.take_profit)

    sl, tp, _ = _validate_tp_sl(side, mark_price, stop_loss, take_profit)

    protective_orders: list[dict[str, Any]] = []
    base_cid = intent_id[:28]

    def place_protective(order_type: str, stop_price: float, suffix: str) -> dict[str, Any]:
        formatted = _round_to_tick(stop_price, tick)
        cid = f"{base_cid}{suffix}"
        return client.place_algo_order(
            symbol=symbol,
            side="SELL" if econ_side == "LONG" else "BUY",
            order_type=order_type,
            trigger_price=formatted,
            close_position=True,
            working_type="MARK_PRICE",
            client_algo_id=cid,
            intent_id=intent_id,
        )

    error_parts: list[str] = []
    if sl is not None:
        try:
            protective_orders.append(place_protective("STOP_MARKET", sl, "_sl"))
        except Exception as exc:
            error_parts.append(f"SL placement returned: {exc}")

    if tp is not None:
        try:
            protective_orders.append(place_protective("TAKE_PROFIT_MARKET", tp, "_tp"))
        except Exception as exc:
            error_parts.append(f"TP placement returned: {exc}")

    # Status is decided by what is actually resting on the exchange, never by
    # which placement calls threw -- an error and the exchange's state are not
    # the same fact. PositionReconciler attaches protection for the same
    # position, so a placement here can legitimately fail with -4130 ("an open
    # stop or take profit order with GTE and closePosition in the direction is
    # existing") while that position is already fully covered. The previous
    # version inferred status from the exceptions and then "rolled back" by
    # cancelling the SL it had just placed whenever the TP call raised -- so a
    # -4130 saying "protection already exists" could strip protection off a
    # live position. Rollback is gone: if cover is missing, the caller retries
    # (PROTECTION_FAILED is retryable, not terminal) and the reconciler also
    # repairs it, both of which are safe when placement is idempotent.
    exit_side = "SELL" if econ_side == "LONG" else "BUY"
    try:
        live_algos = client.get_open_algo_orders(symbol=symbol)
    except Exception as exc:
        # Cannot observe the exchange -> cannot claim the position is covered.
        error_parts.append(f"protection verification failed: {exc}")
        return protective_orders, "PROTECTION_FAILED", "; ".join(error_parts)

    def _resting(order_type_fragment: str) -> bool:
        for o in live_algos:
            if str(o.get("side", "")).upper() != exit_side:
                continue
            if str(o.get("closePosition", "")).lower() not in ("true", "1"):
                continue
            order_type = str(
                o.get("orderType") or o.get("type") or o.get("origType") or o.get("algoType") or ""
            ).upper()
            if order_type_fragment in order_type:
                return True
        return False

    has_sl = _resting("STOP")
    has_tp = _resting("TAKE_PROFIT")

    observed = [
        o for o in live_algos
        if str(o.get("side", "")).upper() == exit_side
        and str(o.get("closePosition", "")).lower() in ("true", "1")
    ]

    missing = []
    if sl is not None and not has_sl:
        missing.append("STOP_MARKET")
    if tp is not None and not has_tp:
        missing.append("TAKE_PROFIT_MARKET")

    if not missing:
        # Exchange confirms cover; placement errors were duplicates/races.
        return observed or protective_orders, "PROTECTED", None

    error_parts.append("unprotected on exchange: " + ", ".join(missing))
    return observed or protective_orders, "PROTECTION_FAILED", "; ".join(error_parts)


class BinanceTestnetExecutor:
    """Adapter that turns a ``TradeIntent`` into a Binance Testnet order.

    - Defaults to dry-run mode unless ``EXECUTION_ENABLED=true``.
    - Persists every intent and every execution result.
    - Keeps Binance-specific symbol/parameter mapping inside this adapter.
    - Relies on ``futures_sdk.place_order`` to enforce the testnet guard.
    - Attaches TP/SL protective orders as soon as an entry is filled.
    """

    def __init__(self, client: Optional[BinanceFuturesClient] = None) -> None:
        self.client = client or get_binance_futures_client()
        self._session_dir: Optional[Path] = None
        raw = os.getenv(EXECUTION_ENABLED_ENV, "false").strip().lower()
        self.execution_enabled = raw in {"1", "true", "yes", "on"}

    def _validate(self, intent: TradeIntent) -> None:
        if not intent.intent_id:
            raise ValueError("intent_id is required")
        if not intent.strategy_id:
            raise ValueError("strategy_id is required")
        if not intent.symbol:
            raise ValueError("symbol is required")
        if intent.side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {intent.side}")
        if intent.order_type not in ("MARKET", "LIMIT"):
            raise ValueError(f"Unsupported order type: {intent.order_type}")
        if intent.order_type == "LIMIT" and intent.limit_price is None:
            raise ValueError("limit_price is required for LIMIT order")
        if intent.quantity is None and intent.notional is None:
            raise ValueError("quantity or notional is required")
        if intent.quantity is not None and (intent.quantity <= 0 or not _finite(intent.quantity)):
            raise ValueError(f"Invalid quantity: {intent.quantity}")
        if intent.notional is not None and (intent.notional <= 0 or not _finite(intent.notional)):
            raise ValueError(f"Invalid notional: {intent.notional}")

    def submit(self, intent: TradeIntent, session_dir: Optional[Path] = None) -> ExecutionResult:
        """Step 4 path: validate, evaluate risk, persist decision, dry-run only."""
        self._session_dir = session_dir
        self._validate(intent)

        from src.trading.risk import (
            BinanceTestnetStateProvider,
            RiskDecisionLedger,
            load_risk_config,
            process_trade_intent_step4,
        )
        from src.trading.risk.session_intent_registry import SessionIntentRegistry
        from src.trading.risk.session_trade_ledger import SessionTradeLedger

        import time

        now_epoch = int(time.time())
        pre_trade_intent = _to_pre_trade_intent(intent)

        # Step 5 idempotency: return an already live-submitted result without re-running risk.
        if session_dir is not None:
            exec_path = session_dir / "executions.jsonl"
            if exec_path.exists():
                for line in exec_path.read_text().strip().splitlines():
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("intent_id") == pre_trade_intent.intent_id and record.get("status") in (
                        "SUBMITTED",
                        "FILLED",
                    ):
                        return ExecutionResult(
                            **{k: v for k, v in record.items() if k in ExecutionResult.__dataclass_fields__}
                        )

        state = BinanceTestnetStateProvider(client=self.client)
        risk_ledger = RiskDecisionLedger(
            session_dir / "risk_decisions.jsonl" if session_dir else Path("/tmp") / "risk_decisions.jsonl"
        )
        trade_ledger = SessionTradeLedger(
            session_dir / "trades.jsonl" if session_dir else Path("/tmp") / "trades.jsonl"
        )
        intent_registry = SessionIntentRegistry(
            session_dir / "intents.jsonl" if session_dir else Path("/tmp") / "intents.jsonl"
        )
        risk_config = load_risk_config()

        step4 = process_trade_intent_step4(
            intent=pre_trade_intent,
            config=risk_config,
            exchange=state,
            intent_registry=intent_registry,
            trade_ledger=trade_ledger,
            risk_ledger=risk_ledger,
            dry_run_executor=self,
            now_epoch=now_epoch,
            execution_enabled=False,
        )

        if step4.status == "APPROVED_DRY_RUN" and step4.dry_run_result is not None:
            if self.execution_enabled:
                return self._submit_real(intent, pre_trade_intent, step4.decision, session_dir)
            return step4.dry_run_result

        actual_notional = float(pre_trade_intent.quantity) * float(pre_trade_intent.market_snapshot.mark_price)
        result = ExecutionResult(
            intent_id=intent.intent_id,
            status="REJECTED",
            exchange="binance",
            environment="testnet",
            error="; ".join(step4.decision.reasons),
            target_notional=float(intent.notional) if intent.notional is not None else None,
            actual_notional=actual_notional,
            leverage=float(pre_trade_intent.requested_leverage),
        )
        _persist_result(session_dir, result)
        return result

    def _attach_protective_orders(
        self,
        pre_trade_intent: Any,
        mark_price: float,
    ) -> tuple[list[dict[str, Any]], str, str | None]:
        """Attach STOP_MARKET (SL) and TAKE_PROFIT_MARKET (TP) closePosition orders.

        Thin wrapper over the standalone `attach_protective_orders` (shared with
        SignalQueueManager.reconcile_pending_entries, which has no
        pre_trade_intent-shaped object to read from). No behavior change here.
        """
        sl = float(pre_trade_intent.stop_loss) if pre_trade_intent.stop_loss is not None else None
        tp = float(pre_trade_intent.take_profit) if pre_trade_intent.take_profit is not None else None
        return attach_protective_orders(
            client=self.client,
            symbol=pre_trade_intent.symbol,
            side=pre_trade_intent.side,
            stop_loss=sl,
            take_profit=tp,
            mark_price=mark_price,
            intent_id=pre_trade_intent.intent_id,
        )

    def _submit_real(
        self,
        intent: TradeIntent,
        pre_trade_intent: Any,
        decision: Any,
        session_dir: Optional[Path] = None,
    ) -> ExecutionResult:
        """Step 5 controlled live Binance Testnet submission."""
        if not self.client.config.is_testnet:
            raise RuntimeError("STEP5_REQUIRES_TESTNET")
        if self.client.config.trading_env != "binance_testnet":
            raise RuntimeError("STEP5_REQUIRES_BINANCE_TESTNET_ENV")
        host = str(self.client.config.base_url).rstrip("/").lower()
        for prefix in ("https://", "http://"):
            host = host.replace(prefix, "")
        if host != "testnet.binancefuture.com":
            raise RuntimeError("STEP5_REQUIRES_TESTNET_HOST")

        # New-entry kill switch, enforced here because this is the last common
        # boundary before a new entry reaches the matching engine: bulk Idim
        # sync, UI dispatch and the direct /binance-testnet/order endpoint all
        # funnel through dispatch_queued_signal into this method, so a future
        # caller cannot route around it. Reduce-only is exempt -- halting new
        # risk must not block closing a position that is already open.
        from src.trading.entry_gate import (
            NEW_ENTRIES_DISABLED_STATUS,
            new_entries_enabled,
            new_entry_block_reason,
        )

        if not pre_trade_intent.reduce_only and not new_entries_enabled():
            reason = new_entry_block_reason()
            logger.warning("Entry blocked for %s: %s", pre_trade_intent.symbol, reason)
            result = ExecutionResult(
                intent_id=intent.intent_id,
                status=NEW_ENTRIES_DISABLED_STATUS,
                exchange="binance",
                environment="testnet",
                error=reason,
                target_notional=float(intent.notional) if intent.notional is not None else None,
                actual_notional=float(pre_trade_intent.quantity)
                * float(pre_trade_intent.market_snapshot.mark_price),
                leverage=float(pre_trade_intent.requested_leverage),
            )
            _persist_result(session_dir, result)
            return result

        # idempotency: do not resubmit an already live-submitted intent
        if session_dir is not None:
            exec_path = session_dir / "executions.jsonl"
            if exec_path.exists():
                for line in exec_path.read_text().strip().splitlines():
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if record.get("intent_id") == pre_trade_intent.intent_id and record.get(
                        "status"
                    ) in ("SUBMITTED", "FILLED"):
                        return ExecutionResult(
                            **{k: v for k, v in record.items() if k in ExecutionResult.__dataclass_fields__}
                        )

        target_notional = float(intent.notional) if intent.notional is not None else None
        actual_notional = float(pre_trade_intent.quantity) * float(pre_trade_intent.market_snapshot.mark_price)
        confirmed_leverage = float(pre_trade_intent.requested_leverage)
        try:
            price = intent.limit_price if pre_trade_intent.order_type == "LIMIT" else None
            response = self.client.place_order(
                symbol=pre_trade_intent.symbol,
                side=pre_trade_intent.side,
                order_type=pre_trade_intent.order_type,
                quantity=float(pre_trade_intent.quantity),
                price=price,
                reduce_only=pre_trade_intent.reduce_only,
                client_order_id=pre_trade_intent.intent_id[:32],
                intent_id=pre_trade_intent.intent_id,
            )
            order = response.get("order") or {}
            exchange_status = (order.get("status") or "NEW").upper()
            order_id = str(order.get("orderId")) if order.get("orderId") else None

            # Market orders on liquid pairs often return NEW first and fill
            # milliseconds later. Confirm the actual fill state before attaching
            # protective closePosition orders.
            if exchange_status != "FILLED" and order_id:
                for _ in range(5):
                    time.sleep(0.2)
                    try:
                        confirmed = self.client.get_order(pre_trade_intent.symbol, order_id=int(order_id))
                        if (confirmed.get("status") or "").upper() == "FILLED" or float(confirmed.get("executedQty", 0) or 0) > 0:
                            order = confirmed
                            exchange_status = (order.get("status") or "NEW").upper()
                            break
                    except Exception:
                        pass

            result_status = "FILLED" if exchange_status == "FILLED" else "SUBMITTED"
            filled_qty = float(order.get("executedQty", 0) or 0)
            filled_price = float(order.get("avgPrice", 0) or order.get("price", 0) or 0)
            result = ExecutionResult(
                intent_id=pre_trade_intent.intent_id,
                status=result_status,
                exchange="binance",
                environment="testnet",
                exchange_order_id=order_id,
                submitted_at=_now_iso(),
                raw_status=response,
                filled_qty=filled_qty,
                filled_price=filled_price,
                target_notional=target_notional,
                actual_notional=actual_notional,
                leverage=confirmed_leverage,
            )

            if result_status == "FILLED" and (
                pre_trade_intent.stop_loss is not None or pre_trade_intent.take_profit is not None
            ):
                mark_price = float(pre_trade_intent.market_snapshot.mark_price)
                protective_orders, protection_status, protection_error = self._attach_protective_orders(
                    pre_trade_intent, mark_price
                )
                result.protective_orders = protective_orders
                result.protection_status = protection_status
                if protection_status == "PROTECTION_FAILED":
                    result.status = "PROTECTION_FAILED"
                    result.error = protection_error or "Protective order(s) failed"
        except Exception as exc:
            logger.warning("Binance live testnet order submission failed for %s: %s", pre_trade_intent.intent_id, exc)
            result = ExecutionResult(
                intent_id=pre_trade_intent.intent_id,
                status="FAILED",
                exchange="binance",
                environment="testnet",
                error=str(exc),
                target_notional=target_notional,
                actual_notional=actual_notional,
                leverage=confirmed_leverage,
            )

        _persist_result(session_dir, result)
        return result

    def submit_dry_run(self, intent: Any, decision: Any, session_dir: Optional[Path] = None) -> ExecutionResult:
        """Step 4 dry-run terminal: record receipt, never call the exchange."""
        intent_record = getattr(intent, "to_dict", lambda: asdict(intent))()
        decision_record = getattr(decision, "to_dict", lambda: asdict(decision))()
        record = {
            "intent_id": getattr(intent, "intent_id", None),
            "intent": intent_record,
            "decision": decision_record,
            "submitted_at": _now_iso(),
            "status": "DRY_RUN",
        }
        persist_dir = session_dir or self._session_dir
        if persist_dir is not None:
            _persist_jsonl(persist_dir / "intents.jsonl", record)
        result = ExecutionResult(
            intent_id=getattr(intent, "intent_id", ""),
            status="DRY_RUN",
            exchange="binance",
            environment="testnet",
        )
        _persist_result(persist_dir, result)
        return result


def _finite(value: float) -> bool:
    import math
    return math.isfinite(value)


def submit_binance_testnet_intent(
    intent: TradeIntent,
    session_dir: Optional[Path] = None,
    client: Optional[BinanceFuturesClient] = None,
) -> ExecutionResult:
    """Native strategy gate: turn a TradeIntent into a ranked signal and dispatch."""
    import json

    trading_env = (os.getenv("TRADING_ENV") or "").strip().lower()
    if trading_env != "binance_testnet":
        return BinanceTestnetExecutor(client=client).submit(intent, session_dir=session_dir)

    from src.trading.signal_queue import SignalQueueManager

    # Load session risk config if available; otherwise fall back to intent snapshot.
    requested_leverage: int = 1
    regime = "NATIVE"
    if session_dir is not None:
        session_path = Path(session_dir) / "session.json"
        if session_path.exists():
            try:
                session = json.loads(session_path.read_text(encoding="utf-8"))
                risk_config = session.get("risk_config", {})
                requested_leverage = int(float(risk_config.get("leverage", 1.0)))
                regime = str(session.get("regime", "NATIVE")).upper()
            except Exception:
                pass
    if requested_leverage == 1:
        requested_leverage = int(float(intent.market_snapshot.get("leverage", 1.0)))

    criteria = {
        "regime": regime,
        "requested_leverage": requested_leverage,
        "volatility": float(intent.market_snapshot.get("volatility", 1.0)),
        "adx14": float(intent.market_snapshot.get("adx14", 30.0)),
        "reason": intent.reason,
        # Previously silently dropped: a caller-supplied stop/target/entry
        # price on the incoming intent would vanish here even though
        # dispatch_queued_signal reads exactly these criteria keys.
        "stop_loss": intent.stop_loss,
        "take_profit": intent.take_profit,
        "entry": intent.limit_price,
    }

    mgr = SignalQueueManager()
    enq = mgr.enqueue_signal(
        symbol=intent.symbol,
        side=intent.side,
        producer="scaffs_native",
        timeframe="5m",
        raw_score=70.0,
        source_signal_id=intent.intent_id,
        criteria_vector=criteria,
        ttl_seconds=600,
    )
    if not enq.get("ok"):
        return ExecutionResult(
            intent_id=intent.intent_id,
            status="REJECTED",
            exchange="binance",
            environment="testnet",
            error=f"signal queue rejected: {enq.get('reason', 'unknown')}",
        )

    dispatch = mgr.dispatch_queued_signal(enq["id"], notional_usd=100.0)
    exec_dict = dispatch.get("execution_result") or {}
    if dispatch.get("ok"):
        return ExecutionResult(**{k: v for k, v in exec_dict.items() if k in ExecutionResult.__dataclass_fields__})

    return ExecutionResult(
        intent_id=intent.intent_id,
        status="REJECTED",
        exchange="binance",
        environment="testnet",
        error=dispatch.get("reason") or dispatch.get("status", "EXECUTION_FAILED"),
    )
