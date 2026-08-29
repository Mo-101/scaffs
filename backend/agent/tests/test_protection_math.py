import unittest
from decimal import Decimal
from src.trading.protection_math import protection_levels, ProtectionPolicy, ProtectionLevels

class TestProtectionMath(unittest.TestCase):
    def test_long_protection_levels(self):
        entry = Decimal("78000.00")
        tick = Decimal("0.10")
        levels = protection_levels(entry=entry, side="LONG", tick_size=tick)
        # SL: 78000 * 0.98 = 76440.00
        # TP: 78000 * 1.04 = 81120.00
        self.assertEqual(levels.stop_loss, Decimal("76440.00"))
        self.assertEqual(levels.take_profit, Decimal("81120.00"))
        self.assertTrue(levels.stop_loss < entry < levels.take_profit)

    def test_short_protection_levels(self):
        entry = Decimal("2500.00")
        tick = Decimal("0.01")
        levels = protection_levels(entry=entry, side="SHORT", tick_size=tick)
        # SL: 2500 * 1.02 = 2550.00
        # TP: 2500 * 0.96 = 2400.00
        self.assertEqual(levels.stop_loss, Decimal("2550.00"))
        self.assertEqual(levels.take_profit, Decimal("2400.00"))
        self.assertTrue(levels.take_profit < entry < levels.stop_loss)

    def test_invalid_entry_throws(self):
        with self.assertRaises(ValueError):
            protection_levels(entry=Decimal("0"), side="LONG", tick_size=Decimal("0.1"))

    def test_tick_rounding_conservative(self):
        # Entry 100.0, tick 0.05, 2% SL -> 98.0, 4% TP -> 104.0
        levels = protection_levels(
            entry=Decimal("100.00"),
            side="LONG",
            tick_size=Decimal("0.05"),
            policy=ProtectionPolicy(stop_pct=Decimal("0.025"), take_profit_pct=Decimal("0.045"))
        )
        # 100 * 0.975 = 97.50
        # 100 * 1.045 = 104.50
        self.assertEqual(levels.stop_loss, Decimal("97.50"))
        self.assertEqual(levels.take_profit, Decimal("104.50"))

if __name__ == "__main__":
    unittest.main()
