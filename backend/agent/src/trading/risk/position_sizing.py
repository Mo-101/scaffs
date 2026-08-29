"""
position_sizing.py

Dynamic position sizing bounded by Initial Margin Utilization (U_IM) headroom.

Core intuition: U_IM headroom is a fuel gauge, not a target. The router should
never let (MAX_U_IM - U_IM) go negative and get treated as spendable notional —
a negative number multiplied into "max size" is not "trade smaller", it's a
sign error wearing a decimal point. This module clamps that explicitly rather
than trusting the caller to check first.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SizingStatus(str, Enum):
    OK = "OK"
    RESIZED = "RESIZED"
    U_IM_LIMIT_EXCEEDED = "U_IM_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class SizingResult:
    status: SizingStatus
    executed_notional: float
    max_notional: float
    target_notional: float
    u_im_before: float
    max_u_im: float
    reason: Optional[str] = None

    @property
    def was_resized(self) -> bool:
        return self.status == SizingStatus.RESIZED


def calculate_dynamic_size(
    margin_balance: float,
    current_u_im: float,
    max_u_im: float,
    leverage: float,
    target_notional: float,
) -> SizingResult:
    """
    MaxNotional      = MarginBalance * (MAX_U_IM - U_IM) * Leverage   [clamped >= 0]
    ExecutedNotional = min(TargetNotional, MaxNotional)

    Returns U_IM_LIMIT_EXCEEDED (executed_notional=0.0) if current_u_im is
    already at or past the ceiling, or if headroom rounds down to zero.
    """
    if margin_balance < 0 or leverage <= 0 or target_notional < 0:
        raise ValueError(
            f"invalid inputs: margin_balance={margin_balance}, "
            f"leverage={leverage}, target_notional={target_notional}"
        )
    if not (0 <= current_u_im) or not (0 < max_u_im <= 1):
        raise ValueError(
            f"invalid U_IM inputs: current_u_im={current_u_im}, max_u_im={max_u_im}"
        )

    if current_u_im >= max_u_im:
        return SizingResult(
            status=SizingStatus.U_IM_LIMIT_EXCEEDED,
            executed_notional=0.0,
            max_notional=0.0,
            target_notional=target_notional,
            u_im_before=current_u_im,
            max_u_im=max_u_im,
            reason=(
                f"current U_IM {current_u_im:.4f} already at/above "
                f"MAX_U_IM {max_u_im:.4f}"
            ),
        )

    headroom_fraction = max_u_im - current_u_im  # guaranteed > 0 here
    max_notional = max(0.0, margin_balance * headroom_fraction * leverage)

    if max_notional <= 0.0:
        return SizingResult(
            status=SizingStatus.U_IM_LIMIT_EXCEEDED,
            executed_notional=0.0,
            max_notional=0.0,
            target_notional=target_notional,
            u_im_before=current_u_im,
            max_u_im=max_u_im,
            reason="computed headroom rounds to zero notional",
        )

    executed_notional = min(target_notional, max_notional)
    status = (
        SizingStatus.RESIZED
        if executed_notional < target_notional
        else SizingStatus.OK
    )

    return SizingResult(
        status=status,
        executed_notional=executed_notional,
        max_notional=max_notional,
        target_notional=target_notional,
        u_im_before=current_u_im,
        max_u_im=max_u_im,
        reason=None if status == SizingStatus.OK else (
            f"target {target_notional:.2f} resized to {executed_notional:.2f} "
            f"(headroom cap {max_notional:.2f})"
        ),
    )
