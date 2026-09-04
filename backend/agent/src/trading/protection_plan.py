"""One authority for the stop/take-profit pair attached to a position.

Before this module, two components independently authored halves of one
protection contract. ``attach_protective_orders`` validated the signal's
boundaries against mark and *dropped* whichever was on the wrong side
(``_validate_tp_sl`` returns ``None`` rather than repairing), then
``PositionReconciler`` noticed the gap and synthesized a replacement from
``ProtectionPolicy``. Neither step is wrong alone; the combination produced
positions whose stop came from the signal and whose target came from policy.

Observed live: TAOUSDT filled at 229.22 against a signal planning entry 215.
The signal stop (210) was below mark so it survived validation; the signal
target (224) was also below mark so it was discarded. The reconciler then
installed 229.22 x 1.04 = 238.39. The position risked 8.4% to make 4% -- a
0.48:1 trade assembled from two halves that were each individually sane.

The rule this module enforces is that a protection pair has ONE provenance:

    SIGNAL stop + SIGNAL target            allowed
    POLICY stop + POLICY target            allowed
    SIGNAL stop + POLICY target            rejected
    POLICY stop + SIGNAL target            rejected

Callers get a complete, validated :class:`ProtectionPlan` or an exception --
never a half-populated pair to fill in themselves.

This module is deliberately pure: Decimal arithmetic, no exchange calls, no
database, no rounding to exchange ticks. Tick normalization happens at the
placement boundary, where the tick size is known; :func:`assert_tick_safe`
exists so that step can prove its rounding did not push a boundary across
entry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal as D
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]
ProtectionSource = Literal["SIGNAL", "POLICY_FALLBACK"]

#: Minimum reward:risk a plan must clear. A signal pair that no longer earns
#: its risk after slippage is not "slightly worse" -- it is a different trade
#: than the one that was approved, so it is discarded wholesale in favour of a
#: coherent policy pair rather than partially honoured.
MIN_REWARD_RISK = D(os.getenv("MIN_REWARD_RISK", "1.5"))

#: Policy fallback distances, matching ProtectionPolicy in protection_math so
#: the two layers cannot drift into disagreeing about what "policy" means.
POLICY_STOP_PCT = D(os.getenv("PROTECTION_STOP_PCT", "0.02"))
POLICY_TAKE_PROFIT_PCT = D(os.getenv("PROTECTION_TAKE_PROFIT_PCT", "0.04"))

#: A stop closer to entry than this is inside the tick/spread noise band and
#: will be triggered by ordinary jitter rather than by the thesis failing.
#: Geometrically valid, economically a coin flip -- so it is rejected and the
#: pair falls back to policy distances.
MIN_STOP_DISTANCE_PCT = D(os.getenv("MIN_STOP_DISTANCE_PCT", "0.0005"))


class ProtectionInvariantError(Exception):
    """A protection pair is missing, geometrically invalid, or under-rewarded.

    Raised only for a pair that cannot be made safe. Pre-fill this means
    "do not open the position". Post-fill the position already exists, so the
    caller must flatten rather than treat the raise as a refusal to act --
    see the module docstring of the placement layer.
    """


class InvertedStopError(ProtectionInvariantError):
    """The stop sits on the wrong side of entry -- an instant stop-out.

    Split out from the base class because this is the single most damaging
    geometry error and deserves to be greppable in isolation: ONGUSDT lost
    37.21 USDT to a long whose stop (0.117848) was above its own fill
    (0.112020), and BNBUSDT lost 12.95 the same way.
    """


class InvertedTakeProfitError(ProtectionInvariantError):
    """The take-profit sits on the wrong side of entry -- it can only lose."""


class RewardRiskTooLowError(ProtectionInvariantError):
    """Geometry is valid but the pair does not earn its risk."""


class StopTooCloseError(ProtectionInvariantError):
    """The stop is inside the noise band and would trigger on a tick."""


@dataclass(frozen=True)
class ProtectionPlan:
    """A complete, single-provenance protection pair for one position."""

    entry: D
    stop: D
    take_profit: D
    source: ProtectionSource
    reward_risk: D


def _reward_risk(side: Side, entry: D, stop: D, take_profit: D) -> D:
    """Reward:risk of a pair, or Decimal(0) when risk is zero/inverted.

    Returning 0 rather than raising keeps this usable as a predicate inside
    the signal-pair check, where an inverted pair should fall back to policy
    rather than propagate an exception.
    """
    if side == "LONG":
        risk = entry - stop
        reward = take_profit - entry
    else:
        risk = stop - entry
        reward = entry - take_profit
    if risk <= D("0") or reward <= D("0"):
        return D("0")
    return reward / risk


def validate_plan(plan: ProtectionPlan, side: Side) -> None:
    """Raise :class:`ProtectionInvariantError` unless the plan is safe to place.

    Checks geometry first, then reward:risk, so a nonsensical pair reports the
    structural problem rather than a derived ratio.
    """
    if side == "LONG":
        if plan.stop >= plan.entry:
            raise InvertedStopError(
                f"INVERTED LONG STOP: stop ({plan.stop}) >= entry ({plan.entry}), "
                f"difference +{plan.stop - plan.entry}. This opens and closes in the "
                f"same breath; aborted."
            )
        if plan.take_profit <= plan.entry:
            raise InvertedTakeProfitError(
                f"INVERTED LONG TAKE PROFIT: take_profit ({plan.take_profit}) <= "
                f"entry ({plan.entry}); the target can only be reached at a loss."
            )
        if plan.stop > plan.entry * (D("1") - MIN_STOP_DISTANCE_PCT):
            raise StopTooCloseError(
                f"LONG stop {plan.stop} is inside the noise band around entry "
                f"{plan.entry}; must be at or below "
                f"{plan.entry * (D('1') - MIN_STOP_DISTANCE_PCT)}"
            )
    elif side == "SHORT":
        if plan.stop <= plan.entry:
            raise InvertedStopError(
                f"INVERTED SHORT STOP: stop ({plan.stop}) <= entry ({plan.entry}), "
                f"difference -{plan.entry - plan.stop}. This opens and closes in the "
                f"same breath; aborted."
            )
        if plan.take_profit >= plan.entry:
            raise InvertedTakeProfitError(
                f"INVERTED SHORT TAKE PROFIT: take_profit ({plan.take_profit}) >= "
                f"entry ({plan.entry}); the target can only be reached at a loss."
            )
        if plan.stop < plan.entry * (D("1") + MIN_STOP_DISTANCE_PCT):
            raise StopTooCloseError(
                f"SHORT stop {plan.stop} is inside the noise band around entry "
                f"{plan.entry}; must be at or above "
                f"{plan.entry * (D('1') + MIN_STOP_DISTANCE_PCT)}"
            )
    else:
        raise ProtectionInvariantError(f"unknown side: {side!r}")

    if plan.reward_risk < MIN_REWARD_RISK:
        raise RewardRiskTooLowError(
            f"protection reward:risk {plan.reward_risk:.4f} is below the required "
            f"{MIN_REWARD_RISK}; entry={plan.entry}, stop={plan.stop}, "
            f"take_profit={plan.take_profit}, source={plan.source}"
        )


def policy_plan(side: Side, entry: D) -> ProtectionPlan:
    """Build a complete POLICY_FALLBACK pair from an actual entry price.

    Raw (untick-rounded) by design -- see the module docstring.
    """
    if entry <= D("0"):
        raise ProtectionInvariantError(f"entry must be positive, got {entry}")

    if side == "LONG":
        stop = entry * (D("1") - POLICY_STOP_PCT)
        take_profit = entry * (D("1") + POLICY_TAKE_PROFIT_PCT)
    else:
        stop = entry * (D("1") + POLICY_STOP_PCT)
        take_profit = entry * (D("1") - POLICY_TAKE_PROFIT_PCT)

    plan = ProtectionPlan(
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        source="POLICY_FALLBACK",
        reward_risk=_reward_risk(side, entry, stop, take_profit),
    )
    validate_plan(plan, side)
    return plan


def build_protection_plan(
    *,
    side: Side,
    actual_entry: D,
    signal_stop: Optional[D],
    signal_take_profit: Optional[D],
) -> ProtectionPlan:
    """Return the one protection pair to place for a position.

    ``actual_entry`` must be the executed fill price post-fill, not the mark
    used to price the entry and not the entry the signal planned. Validating
    against mark is what allowed TAO's target to be judged against 229.22
    while its stop was judged against the same number and kept -- the inputs
    were consistent, but neither was checked as a *pair* against the price
    actually paid.

    The signal's pair is preferred and used whole. If either leg is missing,
    or the pair is geometrically invalid against the real entry, or it no
    longer clears MIN_REWARD_RISK, BOTH legs are discarded and a complete
    policy pair is returned. There is no path that mixes them.
    """
    if actual_entry <= D("0"):
        raise ProtectionInvariantError(f"actual_entry must be positive, got {actual_entry}")

    if signal_stop is not None and signal_take_profit is not None:
        candidate = ProtectionPlan(
            entry=actual_entry,
            stop=signal_stop,
            take_profit=signal_take_profit,
            source="SIGNAL",
            reward_risk=_reward_risk(side, actual_entry, signal_stop, signal_take_profit),
        )
        try:
            validate_plan(candidate, side)
        except ProtectionInvariantError:
            # Fall through to policy. Deliberately swallowed: an unusable
            # signal pair is an expected outcome of slippage, not an error --
            # the caller still receives a valid plan. The discarded pair is
            # reported by the returned plan's source being POLICY_FALLBACK.
            pass
        else:
            return candidate

    return policy_plan(side, actual_entry)


def assert_tick_safe(plan: ProtectionPlan, side: Side, stop: D, take_profit: D) -> None:
    """Verify exchange tick rounding did not invalidate a validated plan.

    Rounding moves a boundary by up to one tick, which on a wide tick relative
    to a tight stop is enough to push it across entry -- turning a valid plan
    into an instant stop-out. The placement layer calls this with its rounded
    values before submitting.
    """
    rounded = ProtectionPlan(
        entry=plan.entry,
        stop=stop,
        take_profit=take_profit,
        source=plan.source,
        reward_risk=_reward_risk(side, plan.entry, stop, take_profit),
    )
    try:
        validate_plan(rounded, side)
    except ProtectionInvariantError as exc:
        raise ProtectionInvariantError(
            f"tick rounding invalidated a valid {plan.source} plan "
            f"(stop {plan.stop} -> {stop}, take_profit {plan.take_profit} -> {take_profit}): {exc}"
        ) from exc
