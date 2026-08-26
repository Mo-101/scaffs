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
    )


class BinanceTestnetExecutor:
    """Adapter that turns a ``TradeIntent`` into a Binance Testnet order.

    - Defaults to dry-run mode unless ``EXECUTION_ENABLED=true``.
    - Persists every intent and every execution result.
    - Keeps Binance-specific symbol/parameter mapping inside this adapter.
    - Relies on ``futures_sdk.place_order`` to enforce the testnet guard.
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

        result = ExecutionResult(
            intent_id=intent.intent_id,
            status="REJECTED",
            exchange="binance",
            environment="testnet",
            error="; ".join(step4.decision.reasons),
        )
        _persist_result(session_dir, result)
        return result

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
            result = ExecutionResult(
                intent_id=pre_trade_intent.intent_id,
                status="SUBMITTED",
                exchange="binance",
                environment="testnet",
                exchange_order_id=str(order.get("orderId")) if order.get("orderId") else None,
                submitted_at=_now_iso(),
                raw_status=response,
            )
        except Exception as exc:
            logger.warning("Binance live testnet order submission failed for %s: %s", pre_trade_intent.intent_id, exc)
            result = ExecutionResult(
                intent_id=pre_trade_intent.intent_id,
                status="FAILED",
                exchange="binance",
                environment="testnet",
                error=str(exc),
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
    """Convenience entry point used by strategy code."""
    return BinanceTestnetExecutor(client=client).submit(intent, session_dir=session_dir)
