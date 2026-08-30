"""Protection status must come from exchange state, not from placement errors.

PositionReconciler and the executor both attach TP/SL for the same position,
so a placement call here can be rejected as a duplicate (Binance -4130) while
that position is fully covered. These tests pin the two properties that
matter: a duplicate rejection is not a failure, and a failed TP never causes
an already-placed SL to be cancelled.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

agent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

from src.trading.connectors.binance.binance_testnet_executor import attach_protective_orders

DUPLICATE = Exception(
    "Binance Futures API error (400): code=-4130 msg=An open stop or take "
    "profit order with GTE and closePosition in the direction is existing."
)


def _algo(order_type: str, side: str = "SELL", trigger: str = "1.0") -> dict:
    return {
        "symbol": "ADAUSDT",
        "side": side,
        "orderType": order_type,
        "stopPrice": trigger,
        "closePosition": "true",
        "clientAlgoId": "ADAUSDT_L_r" + ("sl" if "STOP" in order_type else "tp"),
    }


class FakeClient:
    """Minimal client: records placements/cancels, replays a fixed algo book."""

    def __init__(self, resting, place_raises=None):
        self._resting = resting
        self._place_raises = place_raises or {}
        self.placed: list[str] = []
        self.cancelled: list[str] = []

    def get_price_tick_size(self, symbol):
        return 0.001

    def place_algo_order(self, **kwargs):
        order_type = kwargs["order_type"]
        self.placed.append(order_type)
        exc = self._place_raises.get(order_type)
        if exc:
            raise exc
        return {"algo_id": "new-" + order_type, "orderType": order_type}

    def cancel_algo_order(self, symbol, algo_id=None):
        self.cancelled.append(algo_id)

    def get_open_algo_orders(self, symbol=None):
        return list(self._resting)


def _attach(client):
    return attach_protective_orders(
        client=client,
        symbol="ADAUSDT",
        side="BUY",
        stop_loss=0.196,
        take_profit=0.208,
        mark_price=0.200,
        intent_id="intent-abc",
    )


def test_duplicate_rejection_is_protected_when_exchange_shows_cover():
    """-4130 on both boundaries, but both rest on the exchange -> PROTECTED."""
    client = FakeClient(
        resting=[_algo("STOP_MARKET"), _algo("TAKE_PROFIT_MARKET")],
        place_raises={"STOP_MARKET": DUPLICATE, "TAKE_PROFIT_MARKET": DUPLICATE},
    )
    orders, status, error = _attach(client)

    assert status == "PROTECTED"
    assert error is None
    assert len(orders) == 2


def test_failed_tp_never_cancels_an_existing_stop_loss():
    """The old rollback cancelled the SL whenever TP raised. It must not."""
    client = FakeClient(
        resting=[_algo("STOP_MARKET"), _algo("TAKE_PROFIT_MARKET")],
        place_raises={"TAKE_PROFIT_MARKET": DUPLICATE},
    )
    _, status, _ = _attach(client)

    assert client.cancelled == [], "protection was cancelled in response to a placement error"
    assert status == "PROTECTED"


def test_missing_boundary_on_exchange_is_protection_failed():
    """Placement 'succeeded' but nothing rests on the exchange -> fail closed."""
    client = FakeClient(resting=[])
    _, status, error = _attach(client)

    assert status == "PROTECTION_FAILED"
    assert "STOP_MARKET" in error and "TAKE_PROFIT_MARKET" in error


def test_partial_cover_is_protection_failed():
    """Only the SL rests -> the position is not fully covered."""
    client = FakeClient(resting=[_algo("STOP_MARKET")])
    _, status, error = _attach(client)

    assert status == "PROTECTION_FAILED"
    assert "TAKE_PROFIT_MARKET" in error


def test_unreadable_exchange_fails_closed():
    """If cover cannot be observed, it cannot be claimed."""

    class Blind(FakeClient):
        def get_open_algo_orders(self, symbol=None):
            raise RuntimeError("algo endpoint unavailable")

    _, status, error = _attach(Blind(resting=[]))

    assert status == "PROTECTION_FAILED"
    assert "verification failed" in error


def test_wrong_side_orders_do_not_count_as_cover():
    """A BUY-side algo order does not protect a LONG position."""
    client = FakeClient(
        resting=[_algo("STOP_MARKET", side="BUY"), _algo("TAKE_PROFIT_MARKET", side="BUY")]
    )
    _, status, _ = _attach(client)

    assert status == "PROTECTION_FAILED"
