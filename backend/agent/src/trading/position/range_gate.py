"""Deterministic position-management range gate.

The strategy proposes `stop_loss`, `take_profit`, and optional corridor
metadata. This module turns those into a concrete `HOLD` / `CLOSE` decision
without any model freestyle.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Side = Literal["LONG", "SHORT"]
Action = Literal["HOLD", "CLOSE_LONG", "CLOSE_SHORT"]


@dataclass(frozen=True)
class RangeDecision:
    action: Action
    reason: str
    triggered_boundary: str | None = None
    mark_price: Decimal | None = None


def _close_reason(side: Side, boundary: str) -> str:
    return f"{side} position hit {boundary} boundary"


def evaluate_position(
    side: Side,
    mark_price: Decimal,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
) -> RangeDecision:
    """Return the deterministic action for a managed position.

    Rules:
        LONG  → mark <= stop_loss  -> CLOSE_LONG
        LONG  → mark >= take_profit -> CLOSE_LONG
        SHORT → mark >= stop_loss  -> CLOSE_SHORT
        SHORT → mark <= take_profit -> CLOSE_SHORT
    """
    if side == "LONG":
        if stop_loss is not None and mark_price <= stop_loss:
            return RangeDecision(
                action="CLOSE_LONG",
                reason=_close_reason(side, "stop_loss"),
                triggered_boundary="stop_loss",
                mark_price=mark_price,
            )
        if take_profit is not None and mark_price >= take_profit:
            return RangeDecision(
                action="CLOSE_LONG",
                reason=_close_reason(side, "take_profit"),
                triggered_boundary="take_profit",
                mark_price=mark_price,
            )
        return RangeDecision(action="HOLD", reason="LONG position inside range", mark_price=mark_price)

    # SHORT
    if stop_loss is not None and mark_price >= stop_loss:
        return RangeDecision(
            action="CLOSE_SHORT",
            reason=_close_reason(side, "stop_loss"),
            triggered_boundary="stop_loss",
            mark_price=mark_price,
        )
    if take_profit is not None and mark_price <= take_profit:
        return RangeDecision(
            action="CLOSE_SHORT",
            reason=_close_reason(side, "take_profit"),
            triggered_boundary="take_profit",
            mark_price=mark_price,
        )
    return RangeDecision(action="HOLD", reason="SHORT position inside range", mark_price=mark_price)
