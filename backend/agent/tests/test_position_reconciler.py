"""Unit tests for the Step 2 Position Reconciler."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.position.position_reconciler import PositionReconciler


def _fake_psycopg(monkeypatch, rows):
    class FakeCursor:
        def __init__(self, data):
            self._rows = data
            self._idx = 0

        def execute(self, *args, **kwargs):
            pass

        def fetchone(self):
            if self._idx < len(self._rows):
                row = self._rows[self._idx]
                self._idx += 1
                return row
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return FakeCursor(rows)

        def commit(self):
            pass

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: FakeConn())


class FakeClient:
    def __init__(self):
        self.placed = []

    def get_positions(self):
        return [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.05",
                "markPrice": "20000",
                "entryPrice": "19000",
            }
        ]

    def get_open_algo_orders(self):
        return []

    def place_algo_order(self, **kwargs):
        self.placed.append(kwargs)
        return {"client_algo_id": kwargs.get("client_algo_id")}


def test_protected_position():
    client = FakeClient()
    client.get_open_algo_orders = lambda: [
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "STOP_MARKET",
            "closePosition": True,
            "clientAlgoId": "sl1",
        },
        {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
            "closePosition": True,
            "clientAlgoId": "tp1",
        },
    ]
    rec = PositionReconciler(client=client, dsn="")
    report = rec.run(dry_run=True)
    assert report["positions_count"] == 1
    assert report["positions"][0]["status"] == "PROTECTED"
    assert not client.placed


def test_unprotected_no_origin():
    client = FakeClient()
    rec = PositionReconciler(client=client, dsn="")
    report = rec.run(dry_run=True)
    assert report["positions"][0]["status"] == "ALERT"
    assert "originating" in report["positions"][0]["alert_reason"]


def test_repair_dry_run(monkeypatch):
    client = FakeClient()
    _fake_psycopg(
        monkeypatch,
        [
            (
                "queue-1",
                {
                    "stop_loss": 18000.0,
                    "take_profit": 22000.0,
                    "entry": 19000.0,
                    "regime": "TREND",
                },
            )
        ],
    )
    rec = PositionReconciler(client=client, dsn="")
    report = rec.run(dry_run=True)
    pos = report["positions"][0]
    assert pos["status"] == "REPAIR_PENDING"
    assert len(pos["repairs"]) == 2
    assert not client.placed
    assert pos["repairs"][0]["client_algo_id"].startswith("protect:BTCUSDT:LONG:")


def test_repair_live(monkeypatch):
    client = FakeClient()
    _fake_psycopg(
        monkeypatch,
        [
            (
                "queue-1",
                {
                    "stop_loss": 18000.0,
                    "take_profit": 22000.0,
                    "entry": 19000.0,
                    "regime": "TREND",
                },
            )
        ],
    )
    rec = PositionReconciler(client=client, dsn="")
    report = rec.run(dry_run=False)
    pos = report["positions"][0]
    assert pos["status"] == "PROTECTED"
    assert len(client.placed) == 2
