"""Tests for the Step 4 Binance testnet execution adapter."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

agent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

from src.trading.trade_intent import TradeIntent, ExecutionResult
from src.trading.connectors.binance.binance_testnet_executor import (
    BinanceTestnetExecutor,
    _format_binance_symbol,
    _to_pre_trade_intent,
)


def _minimal_intent(**overrides) -> TradeIntent:
    base = {
        "intent_id": "intent-1",
        "strategy_id": "strategy-1",
        "symbol": "BTC-USDT",
        "side": "BUY",
        "quantity": 0.1,
        "notional": 5000.0,
        "order_type": "MARKET",
        "reason": "rebalance",
        "signal_timestamp": "2026-08-26T06:00:00+00:00",
        "market_snapshot": {
            "price": 50000.0,
            "leverage": 1,
            "timestamp": "2026-08-26T06:00:00+00:00",
            "source": "binance_testnet",
        },
        "trading_env": "binance_testnet",
    }
    base.update(overrides)
    return TradeIntent(**base)


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.place_order.return_value = {"order": {"orderId": "12345"}}
    client.get_account_information.return_value = {"availableBalance": "100000.0"}
    client.get_positions.return_value = []
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"
    client.config.base_url = "https://testnet.binancefuture.com"
    return client


def test_format_symbol_normalization():
    assert _format_binance_symbol("BTC-USDT") == "BTCUSDT"
    assert _format_binance_symbol("BTC/USDT") == "BTCUSDT"
    assert _format_binance_symbol("btc-usdt") == "BTCUSDT"


def test_to_pre_trade_intent_conversion():
    intent = _minimal_intent()
    pre = _to_pre_trade_intent(intent)
    assert pre.symbol == "BTCUSDT"
    assert pre.side == "BUY"
    assert pre.quantity == Decimal("0.1")
    assert pre.market_snapshot.mark_price == Decimal("50000.0")


def test_submit_dry_run_persists_and_returns_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    monkeypatch.setenv("MAX_TRADE_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MAX_POSITION_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MIN_AVAILABLE_BALANCE_USDT", "1")
    monkeypatch.setenv("MAX_MARKET_DATA_AGE_SECONDS", "1000000")

    client = _mock_client()
    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert isinstance(result, ExecutionResult)
    assert result.status == "DRY_RUN"
    assert client.place_order.called is False
    assert (tmp_path / "risk_decisions.jsonl").exists()
    assert (tmp_path / "intents.jsonl").exists()
    assert (tmp_path / "executions.jsonl").exists()

    decision_lines = (tmp_path / "risk_decisions.jsonl").read_text().strip().splitlines()
    assert len(decision_lines) == 1
    decision = json.loads(decision_lines[0])
    assert decision["allowed"] is True


def test_submit_rejects_oversized_intent(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "false")
    monkeypatch.setenv("MAX_TRADE_NOTIONAL_USDT", "1000")
    monkeypatch.setenv("MAX_MARKET_DATA_AGE_SECONDS", "1000000")

    client = _mock_client()
    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert result.status == "REJECTED"
    assert client.place_order.called is False
    assert (tmp_path / "risk_decisions.jsonl").exists()
    assert (tmp_path / "executions.jsonl").exists()


def test_execution_enabled_true_submits_real(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("MAX_TRADE_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MAX_POSITION_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MIN_AVAILABLE_BALANCE_USDT", "1")
    monkeypatch.setenv("MAX_MARKET_DATA_AGE_SECONDS", "1000000")

    client = _mock_client()
    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert result.status == "SUBMITTED"
    assert client.place_order.called is True
    assert (tmp_path / "risk_decisions.jsonl").exists()
    assert (tmp_path / "executions.jsonl").exists()


def test_live_submission_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    monkeypatch.setenv("MAX_TRADE_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MAX_POSITION_NOTIONAL_USDT", "100000")
    monkeypatch.setenv("MIN_AVAILABLE_BALANCE_USDT", "1")
    monkeypatch.setenv("MAX_MARKET_DATA_AGE_SECONDS", "1000000")

    client = _mock_client()
    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    first = executor.submit(intent, session_dir=tmp_path)
    second = executor.submit(intent, session_dir=tmp_path)

    assert first.status == "SUBMITTED"
    assert second.status == "SUBMITTED"
    assert client.place_order.call_count == 1


def test_submit_dry_run_method_returns_dry_run(tmp_path):
    executor = BinanceTestnetExecutor(client=_mock_client())
    from src.trading.risk.pre_trade import TradeIntent as PreTradeIntent, MarketSnapshot

    pre_intent = PreTradeIntent(
        intent_id="i-1",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("0.1"),
        reduce_only=False,
        requested_leverage=Decimal("1"),
        market_snapshot=MarketSnapshot(
            symbol="BTCUSDT",
            mark_price=Decimal("50000"),
            timestamp_epoch=1_000_000,
        ),
    )
    from src.trading.risk.pre_trade import RiskDecision

    decision = RiskDecision(
        intent_id="i-1",
        allowed=True,
        reasons=(),
        requested_notional_usdt=Decimal("5000"),
        projected_position_notional_usdt=Decimal("5000"),
        observed={},
        thresholds={},
        evaluated_at="2026-08-26T06:00:00+00:00",
    )
    result = executor.submit_dry_run(pre_intent, decision, session_dir=tmp_path)
    assert result.status == "DRY_RUN"
    assert (tmp_path / "intents.jsonl").exists()
