from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.trading.risk.pre_trade import (
    AccountSnapshot,
    MarketSnapshot,
    PositionSnapshot,
    RiskConfig,
    TradeIntent,
    evaluate_pre_trade,
)
from src.trading.risk.risk_ledger import RiskDecisionLedger
from src.trading.risk.step4_pipeline import process_trade_intent_step4


NOW = 2_000_000_000


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


def config() -> RiskConfig:
    return RiskConfig(
        max_trade_notional_usdt=D(1000),
        max_position_notional_usdt=D(2000),
        max_leverage=D(5),
        min_available_balance_usdt=D(100),
        max_open_positions=3,
        trade_cooldown_seconds=60,
        allowed_symbols=frozenset({"BTCUSDT", "ETHUSDT"}),
        max_market_data_age_seconds=10,
    )


def intent(
    *,
    symbol="BTCUSDT",
    side="BUY",
    quantity="0.01",
    price="50000",
    age=1,
    leverage="2",
    reduce_only=False,
    intent_id="i-1",
):
    return TradeIntent(
        intent_id=intent_id,
        symbol=symbol,
        side=side,
        order_type="MARKET",
        quantity=D(quantity),
        reduce_only=reduce_only,
        requested_leverage=D(leverage),
        market_snapshot=MarketSnapshot(
            symbol=symbol,
            mark_price=D(price),
            timestamp_epoch=NOW - age,
            status="OK",
        ),
    )


class RiskTests(unittest.TestCase):
    def decide(self, i=None, *, balance="5000", positions=(), prev=False, last=None, positions_status="OK"):
        return evaluate_pre_trade(
            intent=i or intent(),
            account=AccountSnapshot(D(balance), "OK"),
            positions=list(positions),
            positions_status=positions_status,
            previous_intent_exists=prev,
            last_entry_timestamp_epoch=last,
            config=config(),
            now_epoch=NOW,
        )

    def test_approved(self):
        self.assertTrue(self.decide().allowed)

    def test_oversized_notional_rejected(self):
        d = self.decide(intent(quantity="0.03"))  # 1500
        self.assertIn("MAX_TRADE_NOTIONAL_EXCEEDED", d.reasons)

    def test_insufficient_balance_rejected(self):
        d = self.decide(balance="50")
        self.assertIn("INSUFFICIENT_AVAILABLE_BALANCE", d.reasons)

    def test_stale_snapshot_rejected(self):
        d = self.decide(intent(age=11))
        self.assertIn("STALE_OR_INVALID_MARKET_DATA", d.reasons)

    def test_disallowed_symbol_rejected(self):
        d = self.decide(intent(symbol="DOGEUSDT", price="1"))
        self.assertIn("SYMBOL_NOT_ALLOWED", d.reasons)

    def test_leverage_cap_enforced(self):
        d = self.decide(intent(leverage="6"))
        self.assertIn("MAX_LEVERAGE_EXCEEDED", d.reasons)

    def test_duplicate_intent_rejected(self):
        d = self.decide(prev=True)
        self.assertIn("DUPLICATE_INTENT", d.reasons)

    def test_cooldown_enforced(self):
        d = self.decide(last=NOW - 30)
        self.assertIn("TRADE_COOLDOWN_ACTIVE", d.reasons)

    def test_reduce_only_cannot_flip_exposure(self):
        p = PositionSnapshot("BTCUSDT", D("500"), D("2"))
        d = self.decide(
            intent(side="SELL", quantity="0.02", reduce_only=True),  # delta -1000, flips +500 to -500
            positions=[p],
            balance="0",  # risk-reducing path does not require free balance
        )
        self.assertIn("REDUCE_ONLY_WOULD_FLIP_EXPOSURE", d.reasons)

    def test_exchange_state_failure_fails_closed(self):
        d = self.decide(positions_status="ERROR")
        self.assertIn("EXCHANGE_STATE_UNAVAILABLE", d.reasons)

    def test_binance_state_provider_has_positions_method(self):
        from unittest.mock import MagicMock
        from src.trading.risk.binance_state_adapter import BinanceTestnetStateProvider
        mock_client = MagicMock()
        mock_client.config.base_url = "https://testnet.binancefuture.com"
        mock_client.config.is_testnet = True
        mock_client.get_positions.return_value = [{"symbol": "BTCUSDT", "notionalValue": "100", "leverage": "5"}]
        provider = BinanceTestnetStateProvider(client=mock_client)
        status, positions = provider.positions()
        self.assertEqual(status, "OK")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].symbol, "BTCUSDT")



class _Exchange:
    mode = "testnet"
    host = "https://testnet.binancefuture.com"
    is_testnet = True

    def account_snapshot(self):
        return AccountSnapshot(D("5000"), "OK")

    def positions(self):
        return ("OK", [])


class _IntentRegistry:
    def exists(self, intent_id):
        return False


class _TradeLedger:
    def last_entry_timestamp(self, symbol):
        return None


class _DryRun:
    def __init__(self):
        self.calls = 0

    def submit_dry_run(self, intent, decision):
        self.calls += 1
        return {"dry_run": True, "intent_id": intent.intent_id}


class PipelineTests(unittest.TestCase):
    def test_approved_intent_reaches_dry_run_exactly_once_and_never_executes(self):
        with tempfile.TemporaryDirectory() as td:
            sink = RiskDecisionLedger(Path(td) / "risk_decisions.jsonl")
            dry = _DryRun()

            out = process_trade_intent_step4(
                intent=intent(),
                config=config(),
                exchange=_Exchange(),
                intent_registry=_IntentRegistry(),
                trade_ledger=_TradeLedger(),
                risk_ledger=sink,
                dry_run_executor=dry,
                now_epoch=NOW,
                execution_enabled=False,
            )

            self.assertEqual(out.status, "APPROVED_DRY_RUN")
            self.assertFalse(out.execution_sent)
            self.assertEqual(dry.calls, 1)

            rows = [
                json.loads(line)
                for line in (Path(td) / "risk_decisions.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["allowed"])

    def test_step4_refuses_execution_enabled_true(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "STEP4_EXECUTION_MUST_REMAIN_DISABLED"):
                process_trade_intent_step4(
                    intent=intent(),
                    config=config(),
                    exchange=_Exchange(),
                    intent_registry=_IntentRegistry(),
                    trade_ledger=_TradeLedger(),
                    risk_ledger=RiskDecisionLedger(Path(td) / "risk.jsonl"),
                    dry_run_executor=_DryRun(),
                    now_epoch=NOW,
                    execution_enabled=True,
                )


if __name__ == "__main__":
    unittest.main()
