from decimal import Decimal
import unittest
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from guardrails import InvertedStopError, PositionSide
from reconciler import AtomicProtectionReconciler, ProtectionPlan


class StubExchangeClient:
    """Deterministic simulation of Binance USDT-M Futures endpoints."""
    def __init__(self, should_fail_tp: bool = False):
        self.orders: dict = {}
        self.cancelled: list = []
        self.counter = 1000
        self.should_fail_tp = should_fail_tp

    def create_stop_order(self, symbol: str, side: str, quantity: str, stop_price: str, reduce_only: bool) -> dict:
        self.counter += 1
        order_id = str(self.counter)
        self.orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": reduce_only,
            "status": "NEW",
        }
        return {"orderId": order_id, "status": "NEW"}

    def create_tp_order(self, symbol: str, side: str, quantity: str, stop_price: str, reduce_only: bool) -> dict:
        if self.should_fail_tp:
            raise ConnectionResetError("Exchange API socket dropped during TP placement")
        self.counter += 1
        order_id = str(self.counter)
        self.orders[order_id] = {
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": reduce_only,
            "status": "NEW",
        }
        return {"orderId": order_id, "status": "NEW"}

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELED"
        self.cancelled.append(order_id)
        return True


class TestProtectionAndReconciler(unittest.TestCase):

    def test_ong_inverted_stop_is_blocked(self):
        """
        ONGUSDT: BUY fill 0.112020, stop 0.117848
        Must throw InvertedStopError and NEVER hit the exchange.
        """
        exchange = StubExchangeClient()
        reconciler = AtomicProtectionReconciler(exchange)

        plan = ProtectionPlan(
            symbol="ONGUSDT",
            side=PositionSide.LONG,
            position_size=Decimal("3000"),
            fill_price=Decimal("0.112020"),
            stop_loss_price=Decimal("0.117848"),  # INVERTED: Stop is higher than fill
            take_profit_price=Decimal("0.130000"),
        )

        result = reconciler.reconcile(plan=plan, stale_order_ids=["OLD_ONG_STOP"])

        self.assertFalse(result.success)
        self.assertIn("INVERTED LONG STOP DETECTED", str(result.error_reason))
        self.assertEqual(len(exchange.orders), 0)
        self.assertEqual(len(exchange.cancelled), 0)

    def test_bnb_inverted_stop_is_blocked(self):
        """
        BNBUSDT: BUY fill 691.98, stop 695.660
        Must throw InvertedStopError and NEVER hit the exchange.
        """
        exchange = StubExchangeClient()
        reconciler = AtomicProtectionReconciler(exchange)

        plan = ProtectionPlan(
            symbol="BNBUSDT",
            side=PositionSide.LONG,
            position_size=Decimal("1.5"),
            fill_price=Decimal("691.98"),
            stop_loss_price=Decimal("695.660"),  # INVERTED: Stop is higher than fill
            take_profit_price=Decimal("720.00"),
        )

        result = reconciler.reconcile(plan=plan, stale_order_ids=["OLD_BNB_STOP"])

        self.assertFalse(result.success)
        self.assertIn("INVERTED LONG STOP DETECTED", str(result.error_reason))
        self.assertEqual(len(exchange.orders), 0)
        self.assertEqual(len(exchange.cancelled), 0)

    def test_valid_long_placement_replaces_stale_orders(self):
        """
        Valid trade: BUY fill 691.98, stop 680.00, TP 720.00
        Ensures Place-New-Then-Cancel-Stale ordering.
        """
        exchange = StubExchangeClient()
        reconciler = AtomicProtectionReconciler(exchange)

        stale_order_id = "STALE_ORDER_999"
        exchange.orders[stale_order_id] = {"status": "NEW"}

        plan = ProtectionPlan(
            symbol="BNBUSDT",
            side=PositionSide.LONG,
            position_size=Decimal("1.5"),
            fill_price=Decimal("691.98"),
            stop_loss_price=Decimal("680.00"),  # Strictly below fill
            take_profit_price=Decimal("720.00"), # Strictly above fill
        )

        result = reconciler.reconcile(plan=plan, stale_order_ids=[stale_order_id])

        self.assertTrue(result.success)
        self.assertIsNotNone(result.placed_stop_loss_id)
        self.assertIsNotNone(result.placed_take_profit_id)
        self.assertIn(stale_order_id, result.cancelled_order_ids)
        self.assertEqual(exchange.orders[stale_order_id]["status"], "CANCELED")

    def test_partial_failure_triggers_atomic_rollback(self):
        """
        If SL succeeds but TP network call throws, the SL must be rolled back immediately
        to prevent unbalanced exposure.
        """
        exchange = StubExchangeClient(should_fail_tp=True)
        reconciler = AtomicProtectionReconciler(exchange)

        stale_order_id = "OLD_VALID_STOP"
        exchange.orders[stale_order_id] = {"status": "NEW"}

        plan = ProtectionPlan(
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            position_size=Decimal("2.0"),
            fill_price=Decimal("2500.00"),
            stop_loss_price=Decimal("2450.00"),
            take_profit_price=Decimal("2600.00"),
        )

        result = reconciler.reconcile(plan=plan, stale_order_ids=[stale_order_id])

        self.assertFalse(result.success)
        # Verify placed SL was cancelled during rollback
        sl_id = "1001"
        self.assertIn(sl_id, exchange.cancelled)
        self.assertEqual(exchange.orders[sl_id]["status"], "CANCELED")
        # Ensure stale order was NOT cancelled since replacement failed
        self.assertNotIn(stale_order_id, exchange.cancelled)


if __name__ == "__main__":
    unittest.main()
