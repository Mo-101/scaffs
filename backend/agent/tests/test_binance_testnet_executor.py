"""Tests for the Binance testnet execution adapter."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

agent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

os.environ.setdefault("TRADING_ENV", "binance_testnet")

from src.trading.trade_intent import TradeIntent, ExecutionResult
from src.trading.connectors.binance.binance_testnet_executor import (
    BinanceTestnetExecutor,
    _format_binance_symbol,
    submit_binance_testnet_intent,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)


def _minimal_intent(**overrides) -> TradeIntent:
    base = {
        "intent_id": "intent-1",
        "strategy_id": "strategy-1",
        "symbol": "BTC-USDT",
        "side": "BUY",
        "quantity": 0.1,
        "notional": 1000.0,
        "order_type": "MARKET",
        "reason": "rebalance",
        "signal_timestamp": "2026-08-26T06:00:00+00:00",
        "market_snapshot": {"price": 50000.0},
        "trading_env": "binance_testnet",
    }
    base.update(overrides)
    return TradeIntent(**base)


def test_format_symbol_normalization():
    assert _format_binance_symbol("BTC-USDT") == "BTCUSDT"
    assert _format_binance_symbol("BTC/USDT") == "BTCUSDT"
    assert _format_binance_symbol("btc-usdt") == "BTCUSDT"


def test_dry_run_persists_intent_and_result(tmp_path):
    os.environ["EXECUTION_ENABLED"] = "false"
    client = MagicMock()
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert result.status == "DRY_RUN"
    assert result.exchange == "binance"
    assert result.environment == "testnet"
    assert client.place_order.called is False

    intents_file = tmp_path / "intents.jsonl"
    executions_file = tmp_path / "executions.jsonl"
    assert intents_file.exists()
    assert executions_file.exists()

    intent_record = json.loads(intents_file.read_text().strip().splitlines()[0])
    assert intent_record["intent_id"] == "intent-1"
    assert intent_record["side"] == "BUY"
    assert intent_record["execution_enabled"] is False

    result_record = json.loads(executions_file.read_text().strip().splitlines()[0])
    assert result_record["status"] == "DRY_RUN"


def test_execution_enabled_zero_place_order_calls(tmp_path, monkeypatch):
    os.environ["EXECUTION_ENABLED"] = "false"
    client = MagicMock()
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert result.status == "DRY_RUN"
    client.place_order.assert_not_called()


def test_buy_sell_mapping():
    os.environ["EXECUTION_ENABLED"] = "true"
    client = MagicMock()
    client.place_order.return_value = {"order": {"orderId": "12345"}}
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)

    buy_intent = _minimal_intent(side="BUY")
    executor.submit(buy_intent)
    call = client.place_order.call_args
    assert call.kwargs["side"] == "BUY"
    assert call.kwargs["symbol"] == "BTCUSDT"

    sell_intent = _minimal_intent(side="SELL")
    executor.submit(sell_intent)
    call = client.place_order.call_args
    assert call.kwargs["side"] == "SELL"


def test_market_and_limit_mapping():
    os.environ["EXECUTION_ENABLED"] = "true"
    client = MagicMock()
    client.place_order.return_value = {"order": {"orderId": "12345"}}
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)

    market_intent = _minimal_intent(order_type="MARKET")
    executor.submit(market_intent)
    call = client.place_order.call_args
    assert call.kwargs["order_type"] == "MARKET"
    assert call.kwargs["price"] is None

    limit_intent = _minimal_intent(order_type="LIMIT", limit_price=49000.0)
    executor.submit(limit_intent)
    call = client.place_order.call_args
    assert call.kwargs["order_type"] == "LIMIT"
    assert call.kwargs["price"] == 49000.0


def test_reduce_only_passed():
    os.environ["EXECUTION_ENABLED"] = "true"
    client = MagicMock()
    client.place_order.return_value = {"order": {"orderId": "12345"}}
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent(reduce_only=True)
    executor.submit(intent)
    assert client.place_order.call_args.kwargs["reduce_only"] is True


def test_invalid_side_rejected():
    executor = BinanceTestnetExecutor(client=MagicMock())
    intent = _minimal_intent(side="HOLD")
    with pytest.raises(ValueError, match="Invalid side"):
        executor.submit(intent)


def test_unsupported_order_type_rejected():
    executor = BinanceTestnetExecutor(client=MagicMock())
    intent = _minimal_intent(order_type="STOP_MARKET")
    with pytest.raises(ValueError, match="Unsupported order type"):
        executor.submit(intent)


def test_duplicate_intent_id_persists_twice_but_does_not_call_sdk_twice(tmp_path):
    os.environ["EXECUTION_ENABLED"] = "false"
    client = MagicMock()
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    executor.submit(intent, session_dir=tmp_path)
    executor.submit(intent, session_dir=tmp_path)

    assert client.place_order.called is False
    lines = (tmp_path / "intents.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_submission_failure_records_failed_status(tmp_path):
    os.environ["EXECUTION_ENABLED"] = "true"
    client = MagicMock()
    client.place_order.side_effect = RuntimeError("network timeout")
    client.config = MagicMock()
    client.config.is_testnet = True
    client.config.trading_env = "binance_testnet"

    executor = BinanceTestnetExecutor(client=client)
    intent = _minimal_intent()
    result = executor.submit(intent, session_dir=tmp_path)

    assert result.status == "FAILED"
    assert "network timeout" in result.error
