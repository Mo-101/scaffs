import math
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import src.trading.signal_queue as sq_module
from src.trading.signal_queue import SignalQueueManager, _resolve_limit_price, enforce_isolated_margin
from src.trading.trade_intent import ExecutionResult, TradeIntent
import src.trading.connectors.binance.futures_sdk as futures_sdk_module
import src.trading.connectors.binance.binance_testnet_executor as bte_module
import src.trading.risk.binance_state_adapter as risk_state_module

_REBALANCE_CRITERIA = {"regime": "STRONG_UPTREND", "adx14": 35.0}


def _unique_signal_id(label: str) -> str:
    return f"{label}-{uuid.uuid4()}"


class FakeBinanceClient:
    """Extends the dispatch-test fake with order/trade/cancel controls for
    the reconcile-poller tests."""

    def __init__(
        self,
        positions=None,
        margin_type="ISOLATED",
        leverage=5,
        order_response=None,
        trades_response=None,
    ):
        self._positions = positions if positions is not None else []
        self._margin_type = margin_type
        self._leverage = leverage
        self._order_response = order_response or {}
        self._trades_response = trades_response or []
        self.cancel_calls: list[tuple] = []

    def get_positions(self, symbol=None):
        return self._positions

    def get_symbol_margin_type(self, symbol):
        return self._margin_type

    def set_margin_type(self, symbol, margin_type="ISOLATED"):
        return {"code": 200}

    def get_symbol_leverage(self, symbol):
        return self._leverage

    def set_leverage(self, symbol, leverage):
        return {"leverage": leverage}

    def get_ticker_price(self, symbol):
        return 100.0

    def get_quantity_precision(self, symbol):
        return 3

    def get_price_tick_size(self, symbol):
        return 0.01

    def get_order(self, symbol=None, order_id=None, client_order_id=None):
        return self._order_response

    def get_order_trades(self, symbol, order_id):
        return self._trades_response

    def cancel_order(self, symbol, order_id=None, client_order_id=None):
        self.cancel_calls.append((symbol, order_id, client_order_id))
        return {"status": "CANCELED"}


class FakeExecutor:
    last_intent = None
    next_result = None

    def __init__(self, client):
        self.client = client
        self.execution_enabled = False

    def submit(self, intent, session_dir=None):
        FakeExecutor.last_intent = intent
        if FakeExecutor.next_result is not None:
            return FakeExecutor.next_result
        return ExecutionResult(intent_id=intent.intent_id, status="SUBMITTED", exchange_order_id="fake-order-1")


@pytest.fixture(autouse=True)
def _testnet_env(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")


def _enqueue_rebalance_signal(mgr: SignalQueueManager, source_signal_id: str, **overrides) -> dict:
    kwargs = dict(
        symbol="BTCUSDT",
        side="BUY",
        producer="scaffs_picker",
        timeframe="15m",
        raw_score=80.0,
        source_signal_id=source_signal_id,
        criteria_vector=dict(_REBALANCE_CRITERIA),
    )
    kwargs.update(overrides)
    res = mgr.enqueue_signal(**kwargs)
    assert res["ok"] is True, res
    return res


def _insert_resting_entry(
    mgr: SignalQueueManager,
    *,
    status="DISPATCHED",
    dispatched_at=None,
    requested_quantity=1.0,
    filled_quantity=0.0,
    entry_ttl_seconds=900,
    criteria=None,
) -> str:
    """Directly craft a resting-entry row for reconcile_pending_entries tests,
    bypassing the full dispatch flow so these tests stay focused on the
    poller's own behavior."""
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("resting"), criteria_vector=criteria or dict(_REBALANCE_CRITERIA))
    queue_id = enq["id"]
    claim = mgr.claim_signal(queue_id)
    assert claim["ok"] is True
    dispatched_at = dispatched_at or datetime.now(timezone.utc)
    # Unique per call: live_fills has a UNIQUE(exchange_order_id,
    # exchange_fill_id) constraint, so a hardcoded order id would collide
    # with a PREVIOUS test run's already-inserted fill (a different queue_id)
    # and ON CONFLICT DO NOTHING would silently skip this run's insert.
    # Must stay numeric: _reconcile_order does int(order_id) when fetching trades.
    order_id = str(uuid.uuid4().int % 10**12)
    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE paper_trading.signal_queue
            SET status = %s, execution_order_id = %s, execution_client_order_id = %s,
                requested_quantity = %s, filled_quantity = %s, entry_ttl_seconds = %s,
                dispatched_at = %s
            WHERE id = %s;
            """,
            (status, order_id, queue_id[:32], requested_quantity, filled_quantity,
             entry_ttl_seconds, dispatched_at, queue_id),
        )
        conn.commit()
    return queue_id


def _row_status(mgr: SignalQueueManager, queue_id: str) -> dict:
    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, filled_quantity, completed_at FROM paper_trading.signal_queue WHERE id = %s;",
            (queue_id,),
        )
        status, filled_qty, completed_at = cur.fetchone()
    return {
        "status": status,
        "filled_quantity": float(filled_qty) if filled_qty is not None else None,
        "completed_at": completed_at,
    }


def test_dispatch_places_limit_entry_and_leaves_row_pending(monkeypatch):
    fake_client = FakeBinanceClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None
    FakeExecutor.next_result = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("resting-dispatch"))

    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0)

    assert result["ok"] is True
    assert result["status"] == "DISPATCHED"
    assert FakeExecutor.last_intent.order_type == "LIMIT"
    assert FakeExecutor.last_intent.limit_price is not None

    row = _row_status(mgr, enq["id"])
    assert row["status"] == "DISPATCHED"
    assert row["filled_quantity"] == 0
    assert row["completed_at"] is None  # not terminal


def test_reconcile_pending_entries_attaches_protection_on_full_fill(monkeypatch):
    fake_client = FakeBinanceClient(
        order_response={"status": "FILLED", "executedQty": "1.0", "avgPrice": "100.0"},
        trades_response=[{"id": 1, "qty": "1.0", "price": "100.0", "commission": "0.01", "time": 1700000000000}],
    )
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(
        bte_module, "attach_protective_orders",
        lambda **kwargs: ([{"order_id": "sl-1"}], "PROTECTED", None),
    )

    mgr = SignalQueueManager()
    queue_id = _insert_resting_entry(
        mgr, requested_quantity=1.0,
        criteria={"stop_loss": 90.0, "take_profit": 110.0, "regime": "STRONG_UPTREND", "adx14": 35.0},
    )

    result = mgr.reconcile_pending_entries(queue_ids=[queue_id])

    assert result["ok"] is True
    assert {"queue_id": queue_id, "outcome": "PROTECTED"} in result["processed"]
    row = _row_status(mgr, queue_id)
    assert row["status"] == "PROTECTED"
    assert row["filled_quantity"] == 1.0
    assert row["completed_at"] is not None  # now terminal

    # Fill was recorded into paper_trading.live_fills (fixes PositionReconciler's
    # provenance gate for real live positions).
    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT quantity, price FROM paper_trading.live_fills WHERE queue_id = %s;", (queue_id,))
        rows = cur.fetchall()
    assert rows == [(1.0, 100.0)]


def test_reconcile_pending_entries_partial_fill_protects_filled_qty_only(monkeypatch):
    fake_client = FakeBinanceClient(
        order_response={"status": "PARTIALLY_FILLED", "executedQty": "0.4", "avgPrice": "100.0"},
        trades_response=[{"id": 2, "qty": "0.4", "price": "100.0", "commission": "0.005", "time": 1700000000000}],
    )
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(
        bte_module, "attach_protective_orders",
        lambda **kwargs: ([{"order_id": "sl-1"}], "PROTECTED", None),
    )

    mgr = SignalQueueManager()
    queue_id = _insert_resting_entry(
        mgr, requested_quantity=1.0,
        criteria={"stop_loss": 90.0, "take_profit": 110.0, "regime": "STRONG_UPTREND", "adx14": 35.0},
    )

    result = mgr.reconcile_pending_entries(queue_ids=[queue_id])

    row = _row_status(mgr, queue_id)
    # closePosition protective orders don't need an exact quantity -- a
    # partial fill is protected exactly as correctly as a full one.
    assert row["status"] == "PROTECTED"
    assert row["filled_quantity"] == 0.4
    assert {"queue_id": queue_id, "outcome": "PROTECTED"} in result["processed"]


def test_reconcile_pending_entries_protection_failure_stays_retryable(monkeypatch):
    fake_client = FakeBinanceClient(
        order_response={"status": "FILLED", "executedQty": "1.0", "avgPrice": "100.0"},
        trades_response=[{"id": 3, "qty": "1.0", "price": "100.0", "commission": "0.01", "time": 1700000000000}],
    )
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(
        bte_module, "attach_protective_orders",
        lambda **kwargs: ([], "PROTECTION_FAILED", "SL failed: rate limited"),
    )

    mgr = SignalQueueManager()
    queue_id = _insert_resting_entry(
        mgr, requested_quantity=1.0,
        criteria={"stop_loss": 90.0, "take_profit": 110.0, "regime": "STRONG_UPTREND", "adx14": 35.0},
    )

    result = mgr.reconcile_pending_entries(queue_ids=[queue_id])
    row = _row_status(mgr, queue_id)
    assert row["status"] == "PROTECTION_FAILED"
    assert row["completed_at"] is None  # retryable, not terminal

    # A second pass retries -- PROTECTION_FAILED is in _RESTING_ENTRY_STATUSES.
    monkeypatch.setattr(
        bte_module, "attach_protective_orders",
        lambda **kwargs: ([{"order_id": "sl-1"}], "PROTECTED", None),
    )
    result2 = mgr.reconcile_pending_entries(queue_ids=[queue_id])
    row2 = _row_status(mgr, queue_id)
    assert row2["status"] == "PROTECTED"
    assert row2["completed_at"] is not None


def test_reconcile_pending_entries_cancels_on_ttl_with_zero_fill(monkeypatch):
    fake_client = FakeBinanceClient(
        order_response={"status": "NEW", "executedQty": "0"},
        trades_response=[],
    )
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)

    mgr = SignalQueueManager()
    stale_dispatch_time = datetime.now(timezone.utc) - timedelta(seconds=1000)
    queue_id = _insert_resting_entry(
        mgr, dispatched_at=stale_dispatch_time, entry_ttl_seconds=900, filled_quantity=0.0,
    )

    result = mgr.reconcile_pending_entries(queue_ids=[queue_id])

    assert fake_client.cancel_calls, "cancel_order should have been called for a TTL-expired unfilled entry"
    row = _row_status(mgr, queue_id)
    assert row["status"] == "ENTRY_CANCELLED_TTL"
    assert row["completed_at"] is not None
    assert {"queue_id": queue_id, "outcome": "ENTRY_CANCELLED_TTL"} in result["processed"]


def test_risk_pct_sizing_overrides_notional_when_stop_loss_present(monkeypatch):
    fake_client = FakeBinanceClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None
    FakeExecutor.next_result = None

    class FakeSnapshot:
        available_balance_usdt = 10000.0
        # Wallet balance (equity) intentionally differs from available
        # balance -- proves sizing uses equity, not the margin-reserved figure.
        total_wallet_balance_usdt = 10500.0

    class FakeStateProvider:
        def __init__(self, client=None):
            pass

        def account_snapshot(self):
            return FakeSnapshot()

    monkeypatch.setattr(risk_state_module, "BinanceTestnetStateProvider", FakeStateProvider)

    mgr = SignalQueueManager()
    # mark=100.0 (FakeBinanceClient.get_ticker_price), so entry (from criteria)
    # will be ~offset-from-mark; stop_loss below entry gives a known stop distance.
    enq = _enqueue_rebalance_signal(
        mgr, _unique_signal_id("risk-pct"),
        criteria_vector={"regime": "STRONG_UPTREND", "adx14": 35.0, "stop_loss": 90.0},
    )

    result = mgr.dispatch_queued_signal(enq["id"], risk_pct=0.01)

    assert result["ok"] is True
    entry_price = FakeExecutor.last_intent.limit_price
    quantity = FakeExecutor.last_intent.quantity
    # Sized off total_wallet_balance_usdt (equity), not available_balance_usdt;
    # denominator includes the fee/slippage cost buffer; rounded DOWN (floor).
    cost_buffer = entry_price * (sq_module._DEFAULT_ROUND_TRIP_FEE_RATE + sq_module._DEFAULT_STOP_SLIPPAGE_PCT)
    effective_distance = abs(entry_price - 90.0) + cost_buffer
    expected_qty = math.floor((10500.0 * 0.01) / effective_distance / 0.001) * 0.001
    assert quantity == pytest.approx(round(expected_qty, 3), abs=0.001)
    # Not the notional_usd default path (100.0/entry_price would be a very
    # different, much larger quantity at 1% risk on a wide stop).
    assert quantity != pytest.approx(100.0 / entry_price, abs=0.001)


def test_risk_pct_ignored_without_stop_loss(monkeypatch):
    fake_client = FakeBinanceClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None
    FakeExecutor.next_result = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("risk-pct-no-sl"))

    # risk_pct supplied but criteria carries no stop_loss -- must fall back
    # to notional_usd sizing silently, never require a stop_loss.
    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0, risk_pct=0.01)

    assert result["ok"] is True
    entry_price = FakeExecutor.last_intent.limit_price
    quantity = FakeExecutor.last_intent.quantity
    assert quantity * entry_price == pytest.approx(25.0, rel=0.15)


def test_risk_pct_exceeding_max_is_rejected(monkeypatch):
    fake_client = FakeBinanceClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None
    FakeExecutor.next_result = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(
        mgr, _unique_signal_id("risk-pct-too-big"),
        criteria_vector={"regime": "STRONG_UPTREND", "adx14": 35.0, "stop_loss": 90.0},
    )

    # The ceiling is frozen policy, not caller-controlled: a request above it
    # must be rejected outright, never silently clamped.
    over_max = sq_module._MAX_RISK_PCT_PER_TRADE + 0.01
    result = mgr.dispatch_queued_signal(enq["id"], risk_pct=over_max)

    assert result["ok"] is False
    assert result["status"] == "RISK_PCT_EXCEEDS_MAX"
    assert FakeExecutor.last_intent is None  # rejected before any exchange interaction


def test_risk_pct_zero_or_negative_is_rejected(monkeypatch):
    fake_client = FakeBinanceClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None
    FakeExecutor.next_result = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(
        mgr, _unique_signal_id("risk-pct-zero"),
        criteria_vector={"regime": "STRONG_UPTREND", "adx14": 35.0, "stop_loss": 90.0},
    )

    result = mgr.dispatch_queued_signal(enq["id"], risk_pct=0.0)

    assert result["ok"] is False
    assert result["status"] == "RISK_PCT_EXCEEDS_MAX"
    assert FakeExecutor.last_intent is None


def test_entry_price_prefers_caller_supplied_entry_when_valid():
    # BUY, mark=100.0, tick=0.01 -- 95.0 is on the correct (below-mark) side.
    price = _resolve_limit_price("BUY", 100.0, 95.0, 0.01)
    assert price == 95.0


def test_entry_price_falls_back_when_caller_entry_on_wrong_side():
    # BUY, mark=100.0 -- 105.0 is on the WRONG side (above mark for a long
    # entry); must fall back to the offset-from-mark scheme, not raise.
    price = _resolve_limit_price("BUY", 100.0, 105.0, 0.01)
    assert price == pytest.approx(100.0 * (1 - 0.002), abs=0.02)


def test_submit_binance_testnet_intent_forwards_stop_loss_take_profit(monkeypatch):
    captured = {}

    class FakeMgr:
        def __init__(self, *a, **k):
            pass

        def enqueue_signal(self, **kwargs):
            captured["criteria_vector"] = kwargs["criteria_vector"]
            return {"ok": True, "id": "queue-1"}

        def dispatch_queued_signal(self, queue_id=None, **kwargs):
            return {
                "ok": True,
                "status": "DISPATCHED",
                "execution_result": {"intent_id": "queue-1", "status": "SUBMITTED"},
            }

    import src.trading.signal_queue as sq_module
    monkeypatch.setattr(sq_module, "SignalQueueManager", FakeMgr)
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")

    intent = TradeIntent(
        intent_id="intent-1",
        strategy_id="rebalance_equal_weight_v1",
        symbol="BTCUSDT",
        side="BUY",
        quantity=1.0,
        notional=100.0,
        order_type="LIMIT",
        limit_price=95.0,
        stop_loss=90.0,
        take_profit=110.0,
        reason="rebalance",
        market_snapshot={"leverage": 5.0, "volatility": 1.0, "adx14": 30.0},
        trading_env="binance_testnet",
    )
    bte_module.submit_binance_testnet_intent(intent, session_dir=None)

    assert captured["criteria_vector"]["stop_loss"] == 90.0
    assert captured["criteria_vector"]["take_profit"] == 110.0
    assert captured["criteria_vector"]["entry"] == 95.0


def test_enforce_isolated_margin_shared_by_both_order_paths():
    """enforce_isolated_margin is the single fail-closed gate now shared by
    dispatch_queued_signal AND paper_session_routes.place_binance_testnet_order
    -- the latter previously had no margin-mode verification at all, letting
    orders submit under whatever mode the exchange already had configured
    (CROSSED by default)."""
    isolated_client = FakeBinanceClient(margin_type="ISOLATED")
    assert enforce_isolated_margin(isolated_client, "BTCUSDT") is None

    crossed_client = FakeBinanceClient(margin_type="CROSSED")
    reason = enforce_isolated_margin(crossed_client, "BTCUSDT")
    assert reason is not None
    assert "MARGIN_MODE_MISMATCH" in reason
    assert "CROSSED" in reason


def test_idim_feed_bridge_treats_entry_cancelled_ttl_as_retry_eligible(monkeypatch):
    from src.trading.idim_feed_bridge import IdimFeedBridge

    mgr = SignalQueueManager()
    sig_id = _unique_signal_id("ttl-cancelled")
    enq = _enqueue_rebalance_signal(mgr, sig_id)
    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE paper_trading.signal_queue SET status = 'ENTRY_CANCELLED_TTL' WHERE id = %s;",
            (enq["id"],),
        )
        conn.commit()

    bridge = IdimFeedBridge()
    monkeypatch.setattr(
        bridge, "fetch_latest_idim_signals",
        lambda limit=20: [{
            "signal_id": sig_id, "pair": "BTCUSDT", "side": "BUY", "score": 80.0,
            "regime": "STRONG_UPTREND",
        }],
    )

    result = bridge.sync_and_enqueue_signals(auto_dispatch=False)

    # ENTRY_CANCELLED_TTL must NOT appear in the exclusion list -- the entry
    # never filled, no position exists, so re-ingesting it is safe. It will
    # be rejected as a duplicate at the DB level only while a PENDING/CLAIMED/
    # DISPATCHED/PARTIALLY_FILLED row exists, which ENTRY_CANCELLED_TTL is not.
    assert result["rejected_count"] == 0, result["rejected"]
    assert result["enqueued_count"] == 1
