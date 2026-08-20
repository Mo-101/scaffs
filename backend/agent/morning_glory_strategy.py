"""Funding-rate mean-reversion signal used by the Morning Glory worker."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MorningGloryDecision:
    action: str
    score: float | None
    reason: str


def funding_zscore(history: list[float], current_rate: float, window: int) -> float | None:
    sample = [float(value) for value in history[-window:] if math.isfinite(float(value))]
    if len(sample) < max(10, window // 3):
        return None
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / len(sample)
    deviation = variance ** 0.5
    if deviation < 1e-12:
        return 0.0
    return (float(current_rate) - mean) / deviation


def decide(
    score: float | None,
    position_side: str | None,
    entry_z: float,
    exit_z: float,
) -> MorningGloryDecision:
    """Side-aware funding rate state machine.

    Explicitly differentiates FLAT, LONG, SHORT.
    A short entered because funding was strongly positive (longs pay) must be
    closed when funding flips strongly negative (shorts would pay), and vice
    versa.  Reversals are always two distinct steps: CLOSE, then a fresh entry.
    """
    if score is None:
        return MorningGloryDecision("HOLD", None, "insufficient_funding_history")

    side = "flat"
    if position_side is not None:
        p_side_lower = position_side.strip().lower()
        if p_side_lower in ("long", "short"):
            side = p_side_lower

    if side == "short":
        # SHORT, z <= -z_entry -> CLOSE (rather than HOLD)
        if score <= -exit_z or score <= -entry_z:
            return MorningGloryDecision("CLOSE", score, f"funding reversed short: z={score:.4f} <= -{exit_z:.4f} or -{entry_z:.4f}")
        return MorningGloryDecision("HOLD", score, f"short held: z={score:.4f}")

    elif side == "long":
        # LONG, z >= z_entry -> CLOSE (rather than HOLD)
        if score >= exit_z or score >= entry_z:
            return MorningGloryDecision("CLOSE", score, f"funding reversed long: z={score:.4f} >= {exit_z:.4f} or {entry_z:.4f}")
        return MorningGloryDecision("HOLD", score, f"long held: z={score:.4f}")

    else:  # FLAT / None
        if score <= -entry_z:
            return MorningGloryDecision("OPEN_LONG", score, f"negative funding extreme: z={score:.4f}")
        if score >= entry_z:
            return MorningGloryDecision("OPEN_SHORT", score, f"positive funding extreme: z={score:.4f}")
        return MorningGloryDecision("HOLD", score, f"no entry: |z|={abs(score):.4f} < {entry_z:.4f}")
