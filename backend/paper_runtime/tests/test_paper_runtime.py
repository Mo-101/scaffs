#!/usr/bin/env python3
"""Invariants that keep accounting out of the presentation layer.

Run: python3 -m paper_runtime.tests.test_paper_runtime   (from backend/)

Plain unittest, stdlib only -- these must be runnable on a bare python3 with no
install step, because the whole point is that they run everywhere the engine
does.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from .. import metrics as M
from ..driver import MAJORS, StrategySpec, run_replay

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def equity_series(values, step_seconds):
    return [
        {"timestamp": (START + timedelta(seconds=i * step_seconds)).isoformat(), "equity": v}
        for i, v in enumerate(values)
    ]


class TestSamplingRateInvariance(unittest.TestCase):
    """The headline property: UI/tick cadence must not move a strategy metric."""

    def test_oversampling_does_not_change_metrics(self):
        # One underlying equity path observed at 15m.
        base_values = [1000.0 * (1.0 + 0.0004 * i - 0.00002 * (i % 7)) for i in range(200)]
        coarse = equity_series(base_values, 900)

        # The same path observed 60x more often: each 15m value repeated, which
        # is what a 15s dashboard poll against an unchanged balance produces.
        fine_values = [v for v in base_values for _ in range(60)]
        fine = equity_series(fine_values, 15)

        a = M.compute_risk_metrics(coarse, resample_seconds=900)
        b = M.compute_risk_metrics(fine, resample_seconds=900)

        self.assertIsNotNone(a.sharpe)
        self.assertAlmostEqual(a.sharpe, b.sharpe, places=6)
        self.assertAlmostEqual(a.annualized_volatility, b.annualized_volatility, places=6)
        self.assertAlmostEqual(a.max_drawdown, b.max_drawdown, places=9)

    def test_annualization_factor_follows_the_interval(self):
        # sqrt(35040) for 15m -- derived, not a literal 187.18 in the source.
        m = M.compute_risk_metrics(equity_series([100.0 + i for i in range(60)], 900),
                                   resample_seconds=900)
        self.assertAlmostEqual(m.periods_per_year, 35040.0, places=6)
        hourly = M.compute_risk_metrics(equity_series([100.0 + i for i in range(60)], 3600),
                                        resample_seconds=3600)
        self.assertAlmostEqual(hourly.periods_per_year, 8760.0, places=6)


class TestMetricHonesty(unittest.TestCase):
    """Thin data must produce N/A with a reason, never a confident number."""

    def test_short_series_reports_insufficient_samples(self):
        m = M.compute_risk_metrics(equity_series([100.0, 101.0, 102.0], 900), resample_seconds=900)
        self.assertIsNone(m.sharpe)
        self.assertEqual(m.sharpe_status, "insufficient_samples")

    def test_calmar_gated_on_duration_not_just_samples(self):
        # 40 samples at 60s == 40 minutes: enough points, nowhere near enough
        # time to annualize honestly.
        m = M.compute_risk_metrics(
            equity_series([100.0 * (1 + 0.001 * i) for i in range(40)], 60),
            resample_seconds=60,
        )
        self.assertIsNotNone(m.sharpe)
        self.assertIsNone(m.calmar)
        self.assertEqual(m.calmar_status, "insufficient_duration")

    def test_max_drawdown_is_measured_not_constant(self):
        m = M.compute_risk_metrics(
            equity_series([100.0, 120.0, 90.0, 110.0], 900), resample_seconds=900
        )
        self.assertAlmostEqual(m.max_drawdown, 0.25, places=9)   # 120 -> 90

    def test_no_closed_trades_yields_none_not_zero(self):
        stats = M.compute_trade_stats([])
        self.assertEqual(stats.status, "no_closed_trades")
        self.assertIsNone(stats.win_rate)
        self.assertIsNone(stats.profit_factor)

    def test_profit_factor_undefined_without_losses(self):
        stats = M.compute_trade_stats([{"net_pnl": 5.0}, {"net_pnl": 3.0}])
        self.assertIsNone(stats.profit_factor)
        self.assertEqual(stats.win_count, 2)

    def test_trade_stats_reconcile_with_each_other(self):
        rows = [{"net_pnl": v} for v in (10.0, -4.0, 7.5, -2.5, 1.0)]
        s = M.compute_trade_stats(rows)
        self.assertEqual(s.closed_trades, 5)
        self.assertEqual(s.win_count + s.loss_count + s.breakeven_count, 5)
        self.assertAlmostEqual(s.win_rate, 3 / 5)
        self.assertAlmostEqual(s.gross_profit, 18.5)
        self.assertAlmostEqual(s.gross_loss, 6.5)
        self.assertAlmostEqual(s.profit_factor, 18.5 / 6.5)
        self.assertAlmostEqual(s.avg_win, 18.5 / 3)
        self.assertAlmostEqual(s.avg_loss, 6.5 / 2)
        self.assertAlmostEqual(s.realized_net_pnl, 12.0)


class TestEngineDerivedSession(unittest.TestCase):
    """End-to-end: the engine's own ledger must reconcile with the DTO."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_replay(
            StrategySpec(
                session_id="test_replay",
                strategy_id="mean_reversion_v1",
                leverage=5, margin=50.0, symbols=MAJORS,
            ),
            days=5, seed=11, start=START,
        )
        cls.dto = cls.result.dto

    def test_equity_identity_holds(self):
        d = self.dto
        self.assertAlmostEqual(d["starting_equity"] + d["net_pnl"], d["current_equity"], places=6)

    def test_wallet_plus_unrealized_is_equity(self):
        d = self.dto
        self.assertAlmostEqual(
            d["wallet_balance"] + d["unrealized_gross_pnl"], d["current_equity"], places=6
        )

    def test_trade_count_equals_actual_ledger_rows(self):
        # The fixture claimed 30 closed trades while carrying 3 rows.
        d = self.dto
        self.assertEqual(d["metrics"]["trade_stats"]["closed_trades"], len(d["closed_trades"]))

    def test_realized_pnl_is_the_sum_of_closed_trades(self):
        d = self.dto
        self.assertAlmostEqual(
            sum(t["net_pnl"] for t in d["closed_trades"]), d["realized_net_pnl"], places=4
        )

    def test_fees_are_not_double_counted(self):
        # Every closed trade's net_pnl must already be gross minus its own costs.
        for t in self.dto["closed_trades"]:
            expected = (
                t["gross_pnl"] - t["entry_fee"] - t["exit_fee"]
                - t["funding_paid"] - t["liquidation_fee"]
            )
            if t["exit_reason"] != "liquidation":   # liquidation floors at margin
                self.assertAlmostEqual(t["net_pnl"], expected, places=6)

    def test_position_side_is_carried_not_inferred(self):
        for p in self.dto["open_positions"]:
            self.assertIn(p["side"], ("long", "short"))
            self.assertEqual(p["direction"], 1 if p["side"] == "long" else -1)

    def test_tp_sl_are_enforced_by_the_engine(self):
        # No open position may sit beyond its own TP or SL after the engine has
        # processed the final price -- the fixture's core execution failure.
        for p in self.dto["open_positions"]:
            mark, tp, sl = p["mark_price"], p["take_profit_price"], p["stop_loss_price"]
            if p["side"] == "long":
                self.assertLess(mark, tp, f"{p['symbol']} long above its TP but still open")
                self.assertGreater(mark, sl, f"{p['symbol']} long below its SL but still open")
            else:
                self.assertGreater(mark, tp, f"{p['symbol']} short below its TP but still open")
                self.assertLess(mark, sl, f"{p['symbol']} short above its SL but still open")

    def test_no_position_survives_its_liquidation_price(self):
        for p in self.dto["open_positions"]:
            if p["side"] == "long":
                self.assertGreater(p["mark_price"], p["liquidation_price"])
            else:
                self.assertLess(p["mark_price"], p["liquidation_price"])

    def test_exit_reasons_come_from_the_engine(self):
        reasons = {t["exit_reason"] for t in self.dto["closed_trades"]}
        self.assertTrue(reasons)
        self.assertTrue(
            reasons <= {"take_profit", "stop_loss", "liquidation", "trailing_stop",
                        "max_hold", "manual"},
            f"unexpected exit reasons: {reasons}",
        )

    def test_replay_is_deterministic(self):
        again = run_replay(
            StrategySpec(
                session_id="test_replay_repeat",
                strategy_id="mean_reversion_v1",
                leverage=5, margin=50.0, symbols=MAJORS,
            ),
            days=5, seed=11, start=START,
        )
        self.assertAlmostEqual(again.dto["net_pnl"], self.dto["net_pnl"], places=9)
        self.assertEqual(
            again.dto["metrics"]["trade_stats"]["closed_trades"],
            self.dto["metrics"]["trade_stats"]["closed_trades"],
        )


class TestLeverageIsNotAlpha(unittest.TestCase):
    """Doubling leverage on an identical signal must not improve the edge."""

    def test_same_signal_at_2x_leverage_scales_pnl_and_risk_together(self):
        common = dict(strategy_id="mean_reversion_v1", margin=50.0, symbols=MAJORS)
        five = run_replay(StrategySpec(session_id="lev_5x", leverage=5, **common),
                          days=5, seed=3, start=START).dto
        ten = run_replay(StrategySpec(session_id="lev_10x", leverage=10, **common),
                         days=5, seed=3, start=START).dto

        self.assertEqual(
            five["metrics"]["trade_stats"]["closed_trades"],
            ten["metrics"]["trade_stats"]["closed_trades"],
        )
        # P&L roughly doubles; so does drawdown. Risk-adjusted return should not
        # meaningfully improve -- if it does, the metric is rewarding leverage.
        self.assertAlmostEqual(ten["net_pnl"] / five["net_pnl"], 2.0, delta=0.15)
        self.assertGreater(
            ten["metrics"]["risk"]["max_drawdown"], five["metrics"]["risk"]["max_drawdown"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
