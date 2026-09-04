"""Protection-pair invariants.

Pure Decimal math -- no database, no exchange. These must stay runnable
without any DSN so the protection contract can be checked in isolation.
"""

from decimal import Decimal as D

import pytest

from src.trading.protection_plan import (
    MIN_REWARD_RISK,
    ProtectionInvariantError,
    ProtectionPlan,
    assert_tick_safe,
    build_protection_plan,
    policy_plan,
    validate_plan,
)


def test_valid_long_signal_pair_stays_signal_derived():
    plan = build_protection_plan(
        side="LONG",
        actual_entry=D("215"),
        signal_stop=D("210"),
        signal_take_profit=D("224"),
    )
    assert plan.source == "SIGNAL"
    assert plan.stop == D("210")
    assert plan.take_profit == D("224")
    # 9 reward / 5 risk
    assert plan.reward_risk == D("1.8")


def test_valid_short_signal_pair_stays_signal_derived():
    plan = build_protection_plan(
        side="SHORT",
        actual_entry=D("100"),
        signal_stop=D("102"),
        signal_take_profit=D("94"),
    )
    assert plan.source == "SIGNAL"
    assert plan.stop == D("102")
    assert plan.take_profit == D("94")
    assert plan.reward_risk == D("3")


def test_tao_long_target_below_actual_entry_triggers_complete_policy_fallback():
    """The live failure: fill 6.6% above the planned entry.

    Must never yield the observed hybrid stop=210 (signal) + tp=238.39 (policy).
    """
    plan = build_protection_plan(
        side="LONG",
        actual_entry=D("229.22"),
        signal_stop=D("210"),
        signal_take_profit=D("224"),
    )
    assert plan.source == "POLICY_FALLBACK"
    assert plan.stop == D("224.6356")
    assert plan.take_profit == D("238.3888")
    assert plan.stop != D("210"), "signal stop must not survive a policy fallback"
    assert plan.reward_risk == D("2")


def test_short_equivalent_triggers_complete_policy_fallback():
    # Filled well below the planned short entry; the target is now above it.
    plan = build_protection_plan(
        side="SHORT",
        actual_entry=D("100"),
        signal_stop=D("120"),
        signal_take_profit=D("105"),
    )
    assert plan.source == "POLICY_FALLBACK"
    assert plan.stop == D("102")
    assert plan.take_profit == D("96")


def test_invalid_stop_triggers_complete_fallback_not_one_leg_substitution():
    """Stop above entry on a long: an instant stop-out.

    The target is still valid, which is exactly the shape that tempts a
    one-leg repair. Both legs must be replaced.
    """
    plan = build_protection_plan(
        side="LONG",
        actual_entry=D("100"),
        signal_stop=D("101"),
        signal_take_profit=D("110"),
    )
    assert plan.source == "POLICY_FALLBACK"
    assert plan.take_profit != D("110"), "signal target must not survive a policy fallback"
    assert plan.stop == D("98")
    assert plan.take_profit == D("104")


@pytest.mark.parametrize(
    "stop,take_profit",
    [(None, D("224")), (D("210"), None), (None, None)],
)
def test_missing_leg_falls_back_to_complete_policy_pair(stop, take_profit):
    plan = build_protection_plan(
        side="LONG", actual_entry=D("100"), signal_stop=stop, signal_take_profit=take_profit
    )
    assert plan.source == "POLICY_FALLBACK"
    assert plan.stop == D("98")
    assert plan.take_profit == D("104")


def test_minimum_reward_risk_is_enforced():
    """Geometrically valid but under-rewarded signal pairs fall back."""
    # risk 2.0, reward 1.0 -> 0.5:1, below the 1.5 floor.
    plan = build_protection_plan(
        side="LONG",
        actual_entry=D("100"),
        signal_stop=D("98"),
        signal_take_profit=D("101"),
    )
    assert plan.source == "POLICY_FALLBACK"
    assert plan.reward_risk >= MIN_REWARD_RISK


def test_validate_plan_rejects_mixed_provenance_geometry_directly():
    """The exact hybrid that reached the exchange must not validate."""
    hybrid = ProtectionPlan(
        entry=D("229.22"),
        stop=D("210"),
        take_profit=D("238.3888"),
        source="SIGNAL",
        reward_risk=D("0.4805"),
    )
    with pytest.raises(ProtectionInvariantError, match="reward:risk"):
        validate_plan(hybrid, "LONG")


def test_tick_rounding_cannot_move_a_boundary_across_entry():
    plan = policy_plan("LONG", D("100"))
    # A coarse tick that rounds the stop up past entry.
    with pytest.raises(ProtectionInvariantError, match="tick rounding invalidated"):
        assert_tick_safe(plan, "LONG", stop=D("101"), take_profit=plan.take_profit)


def test_tick_safe_accepts_rounding_that_preserves_geometry():
    plan = policy_plan("LONG", D("100"))
    assert_tick_safe(plan, "LONG", stop=D("97.9"), take_profit=D("104.1"))


def test_policy_plan_rejects_nonpositive_entry():
    with pytest.raises(ProtectionInvariantError):
        policy_plan("LONG", D("0"))
