import pytest
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.signal_queue import (
    SignalQueueManager,
    route_signal,
    rank_signals_topsis,
    validate_signal_source_role,
)


def test_absolute_hard_gate_rejection():
    """Verify that signals with raw score < 60.0 are rejected immediately by the hard quality gate."""
    mgr = SignalQueueManager()
    res = mgr.enqueue_signal(
        symbol="BTCUSDT",
        side="BUY",
        raw_score=54.5,
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED_QUALITY_GATE"
    assert "below absolute cutoff" in res["reason"]


def test_two_axis_strategy_routing():
    """Verify the Two-Axis Strategy Router maps criteria to execution workers."""
    # Axis 1: Funding Divergence -> Morning Glory worker
    strat_1, conf_1 = route_signal("BTCUSDT", "BUY", "5m", 75.0, {"funding_rate": 0.0008})
    assert strat_1 == "morning_glory"

    # Axis 2: Bounded Grid (Ranging, low ADX) -> 10x Grid Futures worker
    strat_2, conf_2 = route_signal("ETHUSDT", "BUY", "5m", 70.0, {"regime": "RANGING", "adx14": 18.0, "volatility": 1.1})
    assert strat_2 == "grid_futures_10x"

    # Axis 3: Directional Momentum -> retained equal-weight rebalancer worker
    strat_3, conf_3 = route_signal("SOLUSDT", "BUY", "15m", 80.0, {"regime": "STRONG_UPTREND", "adx14": 35.0})
    assert strat_3 == "rebalance_equal_weight_v1"


def test_topsis_ranking_closeness():
    """Verify TOPSIS multi-criteria closeness ranking orders signals relatively."""
    now = datetime.now(timezone.utc)
    batch = [
        {
            "id": "1",
            "raw_score": 85.0,
            "created_at": now,
            "criteria_vector": {"regime_fit": 90.0, "vol_ratio": 1.5},
        },
        {
            "id": "2",
            "raw_score": 62.0,
            "created_at": now - timedelta(seconds=120),
            "criteria_vector": {"regime_fit": 60.0, "vol_ratio": 0.8},
        },
    ]
    ranked = rank_signals_topsis(batch)
    assert len(ranked) == 2
    assert ranked[0]["id"] == "1"
    assert ranked[0]["topsis_score"] > ranked[1]["topsis_score"]


def test_archive_and_idim_roles_are_separated():
    assert validate_signal_source_role(
        "archive",
        "old-1",
        {},
    ) == "producer 'archive' is archive/backfill data and cannot enter the live execution queue"
    assert validate_signal_source_role(
        "backfill",
        "old-2",
        {},
    ) == "producer 'backfill' is archive/backfill data and cannot enter the live execution queue"
    assert validate_signal_source_role(
        "idim_ikang",
        None,
        {},
    ) == "producer 'idim_ikang' must include source_signal_id from the upstream live signal"
    assert validate_signal_source_role(
        "idim_ikang",
        "sig-live-1",
        {"source_role": "archive"},
    ) == "source role 'archive' is archive/backfill data and cannot enter the live execution queue"
    assert validate_signal_source_role("idim_ikang", "sig-live-2", {}) is None


def test_unknown_worker_target_is_rejected(monkeypatch):
    from src.trading import signal_queue as sq
    monkeypatch.setattr(sq, "route_signal", lambda *_a, **_k: ("candidate_5m_futures", 0.5))
    res = SignalQueueManager().enqueue_signal(
        symbol="BTCUSDT",
        side="BUY",
        producer="scaffs_picker",
        raw_score=80.0,
        source_signal_id="test-1",
        criteria_vector={"regime": "WEIRD"},
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED_UNSUPPORTED_STRATEGY"
    assert "not in the canonical allowlist" in res["reason"]


def test_canonical_strategy_bindings():
    from src.trading.strategy_binding import (
        resolve_worker,
        canonical_id_for_worker,
        allowed_workers,
    )

    assert resolve_worker("periodic_equal_weight_rebalance") == "rebalance_equal_weight_v1"
    assert resolve_worker("bounded_grid_v1", "5x") == "grid_futures_5x"
    assert resolve_worker("bounded_grid_v1", "10x") == "grid_futures_10x"
    assert resolve_worker("funding_rate_zscore") == "morning_glory"

    assert canonical_id_for_worker("grid_futures_5x") == "bounded_grid_v1:5x"
    assert canonical_id_for_worker("grid_futures_10x") == "bounded_grid_v1:10x"
    assert canonical_id_for_worker("rebalance_equal_weight_v1") == "periodic_equal_weight_rebalance"
    assert canonical_id_for_worker("morning_glory") == "funding_rate_zscore"

    assert "rebalance_equal_weight_v1" in allowed_workers()
    assert "candidate_5m_futures" not in allowed_workers()


def test_enqueue_rejects_archive_before_live_queue_insert():
    mgr = SignalQueueManager()
    res = mgr.enqueue_signal(
        symbol="BTCUSDT",
        side="BUY",
        producer="archive",
        source_signal_id="old-signal",
        raw_score=80.0,
    )
    assert res["ok"] is False
    assert res["status"] == "REJECTED_SOURCE_ROLE"
    assert "archive/backfill" in res["reason"]


def test_enqueue_and_pending_retrieval():
    """Verify database persistence, TTL, and pending queue retrieval."""
    mgr = SignalQueueManager()
    res = mgr.enqueue_signal(
        symbol="HYPEUSDT",
        side="LONG",
        producer="idim_ikang",
        timeframe="5m",
        raw_score=78.5,
        source_signal_id="idim-live-hype-1",
        criteria_vector={"regime": "UPTREND", "adx14": 28.0},
        ttl_seconds=300,
    )
    assert res["ok"] is True
    queue_id = res["id"]

    pending = mgr.get_pending_batch(limit=50)
    matched = [s for s in pending if s["id"] == queue_id]
    assert len(matched) == 1
    assert matched[0]["symbol"] == "HYPEUSDT"
    assert matched[0]["raw_score"] == 78.5
    assert matched[0]["topsis_score"] is not None
