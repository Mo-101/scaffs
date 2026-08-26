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
import uuid
from datetime import datetime, timezone
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


class BinanceTestnetExecutor:
    """Adapter that turns a ``TradeIntent`` into a Binance Testnet order.

    - Defaults to dry-run mode unless ``EXECUTION_ENABLED=true``.
    - Persists every intent and every execution result.
    - Keeps Binance-specific symbol/parameter mapping inside this adapter.
    - Relies on ``futures_sdk.place_order`` to enforce the testnet guard.
    """

    def __init__(self, client: Optional[BinanceFuturesClient] = None) -> None:
        self.client = client or get_binance_futures_client()
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
        """Validate, persist, and optionally submit the intent to Binance Testnet."""
        self._validate(intent)

        # Build the canonical audit record before any submission.
        audit = {
            "intent_id": intent.intent_id,
            "strategy_id": intent.strategy_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "quantity": intent.quantity,
            "notional": intent.notional,
            "order_type": intent.order_type,
            "limit_price": intent.limit_price,
            "reduce_only": intent.reduce_only,
            "reason": intent.reason,
            "signal_timestamp": intent.signal_timestamp,
            "market_snapshot": intent.market_snapshot,
            "trading_env": intent.trading_env,
            "execution_enabled": self.execution_enabled,
            "submitted_at": _now_iso(),
        }
        _persist_intent(session_dir, audit)

        if not self.execution_enabled:
            logger.info(
                "DRY_RUN intent %s: %s %s qty=%s notional=%s",
                intent.intent_id,
                intent.side,
                intent.symbol,
                intent.quantity,
                intent.notional,
            )
            result = ExecutionResult(
                intent_id=intent.intent_id,
                status="DRY_RUN",
                exchange="binance",
                environment="testnet",
            )
            _persist_result(session_dir, result)
            return result

        return self._submit(intent, session_dir)

    def _submit(self, intent: TradeIntent, session_dir: Optional[Path] = None) -> ExecutionResult:
        """Real Binance Testnet submission.  The SDK asserts is_testnet."""
        try:
            formatted = _format_binance_symbol(intent.symbol)
            price = intent.limit_price if intent.order_type == "LIMIT" else None
            response = self.client.place_order(
                symbol=formatted,
                side=intent.side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                price=price,
                reduce_only=intent.reduce_only,
                client_order_id=intent.intent_id,
                intent_id=intent.intent_id,
            )
            order = response.get("order") or {}
            result = ExecutionResult(
                intent_id=intent.intent_id,
                status="SUBMITTED",
                exchange="binance",
                environment="testnet",
                exchange_order_id=str(order.get("orderId")) if order.get("orderId") else None,
                submitted_at=_now_iso(),
                raw_status=response,
            )
        except Exception as exc:
            logger.warning("Binance testnet order submission failed for %s: %s", intent.intent_id, exc)
            result = ExecutionResult(
                intent_id=intent.intent_id,
                status="FAILED",
                exchange="binance",
                environment="testnet",
                error=str(exc),
            )

        _persist_result(session_dir, result)
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
