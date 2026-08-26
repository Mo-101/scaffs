"""Tests for Step 6 order-state reconciliation."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.get_order.return_value = {
        "status": "FILLED",
        "avgPrice": "79000.0",
        "executedQty": "0.001",
        "orderId": 123,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
    }
    client.get_order_trades.return_value = [
        {
            "id": 1001,
            "orderId": 123,
            "symbol": "BTCUSDT",
            "price": "79000.0",
            "qty": "0.001",
            "quoteQty": "79.0",
            "commission": "0.03",
            "commissionAsset": "USDT",
            "realizedPnl": "0.0",
            "side": "BUY",
            "time": 1700000000000,
        }
    ]
    return client


def _write_submitted(executions_path: Path, intent_id: str, exchange_order_id: str, symbol: str) -> None:
    executions_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "intent_id": intent_id,
        "status": "SUBMITTED",
        "exchange": "binance",
        "environment": "testnet",
        "exchange_order_id": str(exchange_order_id),
        "submitted_at": "2026-08-26T06:00:00+00:00",
        "raw_status": {"order": {"symbol": symbol}},
        "recorded_at": "2026-08-26T06:00:00+00:00",
    }
    executions_path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_reconcile_filled_order(tmp_path):
    from src.trading.connectors.binance.order_reconciliation import reconcile_orders

    executions_path = tmp_path / "executions.jsonl"
    _write_submitted(executions_path, "i-1", "123", "BTCUSDT")
    client = _mock_client()

    results = reconcile_orders(tmp_path, client)

    assert len(results) == 1
    assert results[0].status == "FILLED"
    assert results[0].filled_qty == pytest.approx(0.001)
    assert results[0].filled_price == pytest.approx(79000.0)
    assert results[0].commission == pytest.approx(0.03)
    assert (tmp_path / "fills.jsonl").exists()
    assert (tmp_path / "executions.jsonl").read_text(encoding="utf-8").count("\n") == 2


def test_reconcile_skips_non_submitted_and_idempotent(tmp_path):
    from src.trading.connectors.binance.order_reconciliation import reconcile_orders

    executions_path = tmp_path / "executions.jsonl"
    executions_path.write_text(
        json.dumps(
            {
                "intent_id": "i-2",
                "status": "FILLED",
                "exchange": "binance",
                "environment": "testnet",
                "exchange_order_id": "124",
                "submitted_at": "2026-08-26T06:00:00+00:00",
                "raw_status": {"order": {"symbol": "BTCUSDT"}},
                "recorded_at": "2026-08-26T06:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    client = _mock_client()

    results = reconcile_orders(tmp_path, client)

    assert len(results) == 0
    client.get_order.assert_not_called()
