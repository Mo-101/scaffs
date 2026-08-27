"""Protection-status vocabulary and dataclasses for position reconciliation."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class ProtectionStatus(str, Enum):
    """Canonical protection reconciliation states."""

    PROTECTED = "PROTECTED"
    UNPROTECTED = "UNPROTECTED"
    PARTIALLY_PROTECTED = "PARTIALLY_PROTECTED"
    REPAIR_PENDING = "REPAIR_PENDING"
    REPAIR_FAILED = "REPAIR_FAILED"
    UNKNOWN = "UNKNOWN"
    ALERT = "ALERT"


@dataclass
class ProtectionBoundary:
    """One TP/SL repair attempt and its deterministic client algo id."""

    order_type: str  # STOP_MARKET or TAKE_PROFIT_MARKET
    trigger_price: float
    client_algo_id: str
    placed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_type": self.order_type,
            "trigger_price": self.trigger_price,
            "client_algo_id": self.client_algo_id,
            "placed": self.placed,
            "error": self.error,
        }


@dataclass
class PositionProtection:
    """Reconciliation result for a single live position."""

    symbol: str
    position_side: str  # LONG or SHORT
    position_amt: float
    mark_price: float
    entry_price: Optional[float] = None
    has_stop_loss: bool = False
    has_take_profit: bool = False
    status: ProtectionStatus = ProtectionStatus.UNPROTECTED
    origin_queue_id: Optional[str] = None
    origin_criteria: dict[str, Any] = field(default_factory=dict)
    repairs: list[ProtectionBoundary] = field(default_factory=list)
    alert_reason: Optional[str] = None
    dry_run: bool = True
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "position_side": self.position_side,
            "position_amt": self.position_amt,
            "mark_price": self.mark_price,
            "entry_price": self.entry_price,
            "has_stop_loss": self.has_stop_loss,
            "has_take_profit": self.has_take_profit,
            "status": self.status.value,
            "origin_queue_id": self.origin_queue_id,
            "origin_criteria": self.origin_criteria,
            "repairs": [r.to_dict() for r in self.repairs],
            "alert_reason": self.alert_reason,
            "dry_run": self.dry_run,
            "note": self.note,
        }
