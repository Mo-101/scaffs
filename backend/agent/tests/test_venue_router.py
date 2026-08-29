import unittest

from src.trading.risk.position_sizing import SizingStatus, calculate_dynamic_size
from src.trading.risk.venue_router import (
    OrderState,
    RoutingStatus,
    VenueAllocationPolicy,
    VenueHealth,
    VenueMarginState,
    VenueRouter,
)


class FakePositionState:
    """Test double for PositionStateProvider."""

    def __init__(self, exposure: dict[str, str] | None = None):
        self._exposure = exposure or {}  # symbol -> venue

    def has_exposure(self, symbol: str, venue: str) -> bool:
        return self._exposure.get(symbol) == venue

    def exposure_venue(self, symbol: str):
        return self._exposure.get(symbol)


class FakeOrderState:
    """Test double for OrderStateProvider."""

    def __init__(self, states: dict[tuple[str, str], OrderState] | None = None):
        self._states = states or {}

    def last_order_state(self, symbol: str, venue: str) -> OrderState:
        return self._states.get((symbol, venue), OrderState.NONE)


def make_router(position_state=None, order_state=None, policy=None) -> VenueRouter:
    router = VenueRouter(
        policy=policy or VenueAllocationPolicy(),
        position_state=position_state or FakePositionState(),
        order_state=order_state or FakeOrderState(),
    )
    for venue, latency in [("binance", 50.0), ("okx", 80.0), ("bybit", 65.0), ("gate", 120.0)]:
        router.update_health(VenueHealth(venue=venue, reachable=True, latency_ms=latency))
        router.update_margin(
            VenueMarginState(
                venue=venue,
                margin_balance=10_000.0,
                current_u_im=0.02,
                maintenance_margin_ratio=0.10,
                free_margin=9_800.0,
            )
        )
    return router


class TestPositionSizing(unittest.TestCase):
    def test_ok_within_headroom(self):
        result = calculate_dynamic_size(
            margin_balance=10_000, current_u_im=0.05, max_u_im=0.15,
            leverage=5, target_notional=1_000,
        )
        self.assertEqual(result.status, SizingStatus.OK)
        self.assertEqual(result.executed_notional, 1_000)

    def test_resized_when_target_exceeds_headroom(self):
        # headroom = (0.15 - 0.10) * 10_000 * 5 = 2_500
        result = calculate_dynamic_size(
            margin_balance=10_000, current_u_im=0.10, max_u_im=0.15,
            leverage=5, target_notional=50_000,
        )
        self.assertEqual(result.status, SizingStatus.RESIZED)
        self.assertAlmostEqual(result.executed_notional, 2_500.0)

    def test_blocked_when_u_im_at_ceiling(self):
        result = calculate_dynamic_size(
            margin_balance=10_000, current_u_im=0.15, max_u_im=0.15,
            leverage=5, target_notional=1_000,
        )
        self.assertEqual(result.status, SizingStatus.U_IM_LIMIT_EXCEEDED)
        self.assertEqual(result.executed_notional, 0.0)

    def test_blocked_when_u_im_past_ceiling_no_negative_notional(self):
        result = calculate_dynamic_size(
            margin_balance=10_000, current_u_im=0.20, max_u_im=0.15,
            leverage=5, target_notional=1_000,
        )
        self.assertEqual(result.status, SizingStatus.U_IM_LIMIT_EXCEEDED)
        self.assertGreaterEqual(result.executed_notional, 0.0)


class TestVenueRanking(unittest.TestCase):
    def test_lowest_latency_highest_headroom_wins_when_tied_otherwise(self):
        router = make_router()
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.ROUTED)
        self.assertEqual(decision.selected_venue, "binance")

    def test_unreachable_venue_excluded_from_ranking(self):
        router = make_router()
        router.update_health(VenueHealth(venue="binance", reachable=False, latency_ms=10.0))
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.ROUTED)
        self.assertNotEqual(decision.selected_venue, "binance")

    def test_no_eligible_venue_when_all_over_u_im_cap(self):
        router = make_router()
        for venue in ("binance", "okx", "bybit", "gate"):
            router.update_margin(
                VenueMarginState(
                    venue=venue, margin_balance=10_000, current_u_im=0.20,
                    maintenance_margin_ratio=0.10, free_margin=0.0,
                )
            )
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.NO_ELIGIBLE_VENUE)

    def test_u_im_limit_exceeded_status_on_best_venue_when_pushed_over(self):
        router = make_router()
        for venue in ("binance", "okx", "bybit", "gate"):
            router.update_margin(
                VenueMarginState(
                    venue=venue, margin_balance=10_000, current_u_im=0.149,
                    maintenance_margin_ratio=0.10, free_margin=100.0,
                )
            )
        decision = router.select_venue("BTCUSDT", target_notional=1_000_000, leverage=1)
        self.assertEqual(decision.status, RoutingStatus.ROUTED)
        self.assertLess(decision.allocated_notional, 1_000_000)


class TestVenueAffinityLock(unittest.TestCase):
    def test_symbol_with_open_exposure_stays_on_its_venue_even_if_unhealthy(self):
        position_state = FakePositionState(exposure={"BTCUSDT": "gate"})
        router = make_router(position_state=position_state)
        router.update_health(VenueHealth(venue="gate", reachable=True, latency_ms=999.0))
        router.update_margin(
            VenueMarginState(
                venue="gate", margin_balance=10_000, current_u_im=0.001,
                maintenance_margin_ratio=0.10, free_margin=9_990.0,
            )
        )
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.VENUE_AFFINITY_LOCKED)
        self.assertEqual(decision.selected_venue, "gate")

    def test_no_failover_when_locked_venue_exceeds_u_im(self):
        position_state = FakePositionState(exposure={"BTCUSDT": "gate"})
        router = make_router(position_state=position_state)
        router.update_margin(
            VenueMarginState(
                venue="gate", margin_balance=10_000, current_u_im=0.20,
                maintenance_margin_ratio=0.10, free_margin=0.0,
            )
        )
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.U_IM_LIMIT_EXCEEDED)
        self.assertEqual(decision.selected_venue, "gate")


class TestUnknownOrderStateGuard(unittest.TestCase):
    def test_unknown_order_state_blocks_cross_venue_resubmission(self):
        position_state = FakePositionState(exposure={"BTCUSDT": "binance"})
        order_state = FakeOrderState(states={("BTCUSDT", "binance"): OrderState.UNKNOWN})
        router = make_router(position_state=position_state, order_state=order_state)
        decision = router.select_venue("BTCUSDT", target_notional=1_000, leverage=3)
        self.assertEqual(decision.status, RoutingStatus.AWAITING_RECONCILIATION)
        self.assertIsNone(decision.selected_venue)


if __name__ == "__main__":
    unittest.main()
