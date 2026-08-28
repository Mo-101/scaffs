import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.signal_queue import (
    SignalQueueManager,
    compute_absolute_quality_score,
    rank_signals_topsis,
    validate_signal_source_role,
)
from src.trading.trade_intent import ExecutionResult
import src.trading.connectors.binance.futures_sdk as futures_sdk_module
import src.trading.connectors.binance.binance_testnet_executor as bte_module


# Criteria that reliably route to Axis 3 (rebalance_equal_weight_v1, target
# leverage 5x, MARKET order) -- avoids funding/grid branches entirely so the
# dispatch tests below only need to stub the leverage/margin/order-sizing
# calls a MARKET rebalance actually makes.
_REBALANCE_CRITERIA = {"regime": "STRONG_UPTREND", "adx14": 35.0}


class FakeBinanceClient:
    """Minimal stand-in for BinanceFuturesClient, behavior set per test."""

    def __init__(self, positions=None, positions_error=None, margin_type="ISOLATED", leverage=5):
        self._positions = positions if positions is not None else []
        self._positions_error = positions_error
        self._margin_type = margin_type
        self._leverage = leverage

    def get_positions(self, symbol=None):
        if self._positions_error is not None:
            raise self._positions_error
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


class FakeExecutor:
    """Stand-in for BinanceTestnetExecutor -- records the TradeIntent it
    receives instead of talking to Binance, so dispatch tests can assert on
    what was actually built without a live testnet call."""

    last_intent = None

    def __init__(self, client):
        self.client = client
        self.execution_enabled = False

    def submit(self, intent, session_dir=None):
        FakeExecutor.last_intent = intent
        return ExecutionResult(intent_id=intent.intent_id, status="SUBMITTED", exchange_order_id="fake-order-1")


@pytest.fixture(autouse=True)
def _testnet_env(monkeypatch):
    # BinanceFuturesConfig.from_env() (called inside check_position_collision)
    # raises if TRADING_ENV is unset -- pin it so these tests don't depend on
    # ambient shell state.
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")


def _unique_signal_id(label: str) -> str:
    # The active-signal uniqueness constraint (migrations/010) persists across
    # test runs against a shared dev database, so a fixed literal id would
    # only enqueue successfully once. Suffix with a fresh uuid per call.
    return f"{label}-{uuid.uuid4()}"


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


def test_claim_signal_is_atomic_second_caller_rejected():
    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("claim-race"))
    queue_id = enq["id"]

    first = mgr.claim_signal(queue_id)
    assert first["ok"] is True
    assert first["claim_token"]

    second = mgr.claim_signal(queue_id)
    assert second["ok"] is False
    assert second["status"] == "ALREADY_CLAIMED"
    assert second["current_status"] == "CLAIMED"


def test_dispatch_blocks_when_collision_check_raises(monkeypatch):
    fake_client = FakeBinanceClient(positions_error=RuntimeError("position-risk API unreachable"))
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("collision-unknown"))

    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0)

    assert result["ok"] is False
    assert result["status"] == "COLLISION_UNKNOWN"
    assert FakeExecutor.last_intent is None  # never reached the executor

    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM paper_trading.signal_queue WHERE id = %s;", (enq["id"],))
        assert cur.fetchone()[0] == "COLLISION_UNKNOWN"


def test_dispatch_blocks_on_margin_mode_mismatch(monkeypatch):
    fake_client = FakeBinanceClient(margin_type="CROSSED")
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("margin-mismatch"))

    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0)

    assert result["ok"] is False
    assert result["status"] == "MARGIN_MODE_MISMATCH_BLOCKED"
    assert "CROSSED" in result["reason"]
    assert FakeExecutor.last_intent is None


def test_dispatch_blocks_on_leverage_mismatch(monkeypatch):
    # rebalance_equal_weight_v1's target leverage is 5x; report back 3x confirmed.
    fake_client = FakeBinanceClient(margin_type="ISOLATED", leverage=3)
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None

    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(mgr, _unique_signal_id("leverage-mismatch"))

    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0)

    assert result["ok"] is False
    assert result["status"] == "LEVERAGE_MISMATCH_BLOCKED"
    assert "5" in result["reason"] and "3" in result["reason"]
    assert FakeExecutor.last_intent is None


def test_dispatch_preserves_original_signal_timestamp(monkeypatch):
    fake_client = FakeBinanceClient(margin_type="ISOLATED", leverage=5)
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", FakeExecutor)
    FakeExecutor.last_intent = None

    past_timestamp = "2026-01-01T00:00:00+00:00"
    mgr = SignalQueueManager()
    enq = _enqueue_rebalance_signal(
        mgr, _unique_signal_id("provenance"), signal_timestamp=past_timestamp,
    )

    result = mgr.dispatch_queued_signal(enq["id"], notional_usd=25.0)

    assert result["ok"] is True
    assert result["status"] == "DISPATCHED"
    assert FakeExecutor.last_intent is not None
    # Compare the actual instant, not the raw string: Postgres round-trips a
    # TIMESTAMPTZ in the session's local offset, so the ISO string's offset
    # may differ from what was sent even though it names the same instant.
    captured_dt = datetime.fromisoformat(FakeExecutor.last_intent.signal_timestamp)
    expected_dt = datetime.fromisoformat(past_timestamp)
    assert captured_dt == expected_dt
    # market_snapshot's own timestamp is legitimately dispatch-time "now",
    # not the signal's origin -- must NOT be the same instant.
    market_ts = datetime.fromisoformat(FakeExecutor.last_intent.market_snapshot["timestamp"])
    assert market_ts != expected_dt


def test_duplicate_source_signal_id_rejected_at_db_level():
    mgr = SignalQueueManager()
    sig_id = _unique_signal_id("dup-check")

    first = _enqueue_rebalance_signal(mgr, sig_id)

    second = mgr.enqueue_signal(
        symbol="BTCUSDT", side="BUY", producer="scaffs_picker", timeframe="15m",
        raw_score=80.0, source_signal_id=sig_id, criteria_vector=dict(_REBALANCE_CRITERIA),
    )
    assert second["ok"] is False
    assert second["status"] == "REJECTED_DUPLICATE_SIGNAL"

    # Once the first row is no longer active, the same source_signal_id may
    # be legitimately re-ingested.
    with psycopg.connect(mgr.dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE paper_trading.signal_queue SET status = 'EXPIRED' WHERE id = %s;",
            (first["id"],),
        )
        conn.commit()

    third = mgr.enqueue_signal(
        symbol="BTCUSDT", side="BUY", producer="scaffs_picker", timeframe="15m",
        raw_score=80.0, source_signal_id=sig_id, criteria_vector=dict(_REBALANCE_CRITERIA),
    )
    assert third["ok"] is True


def test_unknown_producer_rejected():
    reason = validate_signal_source_role("some_new_bot", "id-1", {})
    assert reason == (
        "producer 'some_new_bot' is not a recognized producer identity and "
        "cannot enter the live execution queue"
    )

    mgr = SignalQueueManager()
    res = mgr.enqueue_signal(
        symbol="BTCUSDT", side="BUY", producer="some_new_bot", timeframe="15m",
        raw_score=80.0, source_signal_id=_unique_signal_id("unknown-producer"),
        criteria_vector=dict(_REBALANCE_CRITERIA),
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED_UNKNOWN_PRODUCER"


def test_absolute_quality_score_is_batch_independent():
    now = datetime.now(timezone.utc)
    crit = {"regime_fit": 80.0, "vol_ratio": 1.2}

    # Same signal input always yields the same absolute score -- there is no
    # "batch" parameter for it to depend on.
    score_a = compute_absolute_quality_score(75.0, crit, None, now)
    score_b = compute_absolute_quality_score(75.0, crit, None, now)
    assert score_a == score_b

    # Contrast with rank_signals_topsis, which IS relative to whatever else
    # is in the batch -- the same signal's topsis_score changes depending on
    # its competitors.
    signal = {"id": "a", "raw_score": 75.0, "created_at": now, "criteria_vector": crit}

    solo_batch = [dict(signal)]
    rank_signals_topsis(solo_batch)
    score_in_solo_batch = solo_batch[0]["topsis_score"]

    competing_batch = [
        dict(signal),
        {
            "id": "b", "raw_score": 95.0, "created_at": now,
            "criteria_vector": {"regime_fit": 95.0, "vol_ratio": 2.0},
        },
    ]
    rank_signals_topsis(competing_batch)
    score_in_competing_batch = competing_batch[0]["topsis_score"]

    assert score_in_solo_batch != score_in_competing_batch
