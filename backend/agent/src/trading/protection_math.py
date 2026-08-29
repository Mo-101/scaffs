"""Centralized symbolic protection math and tick normalization for Scaffs trading engine.

Calculates underlying price-distance boundaries for Stop-Loss (SL) and Take-Profit (TP):
  LONG:  SL = E * (1 - delta_sl),  TP = E * (1 + delta_tp)
  SHORT: SL = E * (1 + delta_sl),  TP = E * (1 - delta_tp)

Normalizes trigger prices conservatively to exchange tick size:
  - LONG:  SL rounded CEILING, TP rounded CEILING
  - SHORT: SL rounded FLOOR,   TP rounded FLOOR
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

Side = Literal["LONG", "SHORT"]
D = Decimal


@dataclass(frozen=True)
class ProtectionPolicy:
    stop_pct: Decimal = D("0.02")
    take_profit_pct: Decimal = D("0.04")


@dataclass(frozen=True)
class ProtectionLevels:
    stop_loss: Decimal
    take_profit: Decimal


def _round_to_tick(price: Decimal, tick: Decimal, rounding: str) -> Decimal:
    if tick <= D("0"):
        return price
    units = (price / tick).to_integral_value(rounding=rounding)
    return units * tick


def protection_levels(
    *,
    entry: Decimal,
    side: Side,
    tick_size: Decimal,
    policy: ProtectionPolicy = ProtectionPolicy(),
) -> ProtectionLevels:
    """Calculates tick-normalized, geometrically verified TP/SL levels."""
    if entry <= D("0") or tick_size <= D("0"):
        raise ValueError("entry and tick_size must be positive")
    if not (D("0") < policy.stop_pct < D("1")):
        raise ValueError("stop_pct must be in (0, 1)")
    if policy.take_profit_pct <= D("0"):
        raise ValueError("take_profit_pct must be positive")

    direction = D("1") if side == "LONG" else D("-1")
    raw_sl = entry * (D("1") - direction * policy.stop_pct)
    raw_tp = entry * (D("1") + direction * policy.take_profit_pct)

    # Conservative tick normalization:
    # SL never increases requested loss distance.
    # TP never decreases requested reward distance.
    if side == "LONG":
        sl = _round_to_tick(raw_sl, tick_size, ROUND_CEILING)
        tp = _round_to_tick(raw_tp, tick_size, ROUND_CEILING)
    else:
        sl = _round_to_tick(raw_sl, tick_size, ROUND_FLOOR)
        tp = _round_to_tick(raw_tp, tick_size, ROUND_FLOOR)

    if side == "LONG" and not (sl < entry < tp):
        raise ValueError(f"invalid LONG protection geometry: sl={sl}, entry={entry}, tp={tp}")
    if side == "SHORT" and not (tp < entry < sl):
        raise ValueError(f"invalid SHORT protection geometry: tp={tp}, entry={entry}, sl={sl}")

    return ProtectionLevels(stop_loss=sl, take_profit=tp)
