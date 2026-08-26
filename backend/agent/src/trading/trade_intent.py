"""Normalized, exchange-agnostic trade intent used by Scaffs strategy code."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """A strategy decision to trade, before any exchange-specific translation."""

    intent_id: str
    strategy_id: str
    symbol: str  # user-facing symbol, e.g. BTC-USDT
    side: OrderSide
    quantity: Optional[float] = None
    notional: Optional[float] = None
    order_type: OrderType = "MARKET"
    limit_price: Optional[float] = None
    reduce_only: bool = False
    reason: str = ""
    signal_timestamp: str = ""
    market_snapshot: Optional[dict[str, Any]] = None
    trading_env: str = "paper"
    execution_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Normalized outcome of an execution attempt, independent of exchange."""

    intent_id: str
    status: Literal[
        "DRY_RUN", "SUBMITTED", "FILLED", "PARTIALLY_FILLED", "CANCELED", "EXPIRED", "FAILED", "REJECTED"
    ]
    exchange: str = "binance"
    environment: str = "testnet"
    exchange_order_id: Optional[str] = None
    submitted_at: Optional[str] = None
    raw_status: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    filled_price: Optional[float] = None
    filled_qty: Optional[float] = None
    commission: Optional[float] = None
    realized_pnl: Optional[float] = None
    target_notional: Optional[float] = None
    actual_notional: Optional[float] = None
    leverage: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
