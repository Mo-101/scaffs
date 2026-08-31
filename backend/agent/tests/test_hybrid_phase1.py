"""Unit tests for Phase 1 Hybrid Portfolio Allocator."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from src.trading.hybrid import (
    SignalProposal,
    HybridProposalRouter,
    from_idim,
    from_picker,
    from_grid,
    from_morning_glory,
)

def test_signal_proposal_validation():
    now = datetime.now(timezone.utc)
    proposal = SignalProposal(
        producer="idim_ikang",
        strategy_family="directional",
        strategy_version="1.0.0",
        git_sha="abcdef",
        symbol="BTC-USDT",
        side="BUY",
        generated_at=now,
        valid_until=now + timedelta(seconds=600),
        raw_score=75.0,
        reliability=0.85,
    )
    assert proposal.symbol == "BTC-USDT"
    assert proposal.side == "BUY"
    assert proposal.shadow_only is True
    assert len(proposal.idempotency_key) == 64

def test_invalid_strategy_family():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="Invalid strategy_family"):
        SignalProposal(
            producer="test",
            strategy_family="invalid_family",
            strategy_version="1.0",
            git_sha="sha",
            symbol="BTC-USDT",
            side="BUY",
            generated_at=now,
            valid_until=now + timedelta(seconds=300),
        )

def test_engine_adapters():
    # Test Idim
    idim_sig = {"pair": "SOL-USDT", "side": "BUY", "score": 82.0, "entry": 100.0, "stop_loss": 98.0, "take_profit": 105.0}
    p1 = from_idim(idim_sig)
    assert p1.producer == "idim_ikang"
    assert p1.strategy_family == "directional"
    assert p1.symbol == "SOL-USDT"

    # Test Picker
    picker_sig = {"symbol": "ETH-USDT", "side": "SELL", "score": 68.0}
    p2 = from_picker(picker_sig)
    assert p2.producer == "scaffs_picker"
    assert p2.strategy_family == "momentum"
    assert p2.side == "SELL"

    # Test Grid
    grid_sig = {"symbol": "BNB-USDT", "side": "BUY", "grid_confidence": 75.0}
    p3 = from_grid(grid_sig)
    assert p3.producer == "grid_v3"
    assert p3.strategy_family == "mean_reversion"

    # Test Morning Glory
    mg_sig = {"symbol": "BTC-USDT", "side": "BUY", "annualized_yield_pct": 22.5}
    p4 = from_morning_glory(mg_sig)
    assert p4.producer == "morning_glory"
    assert p4.strategy_family == "funding_arbitrage"

def test_router_db_submission():
    dsn = "postgresql:///mostar?host=/var/run/postgresql&port=5433&user=idona"
    router = HybridProposalRouter(dsn=dsn)
    idim_sig = {"pair": "BTC-USDT", "side": "BUY", "score": 90.0, "entry": 78000.0, "stop_loss": 77000.0, "take_profit": 80000.0}
    proposal = from_idim(idim_sig)

    res = router.submit_proposal(proposal)
    assert res["producer"] == "idim_ikang"
    assert res["decision"] == "SHADOW_ONLY"
    assert res["shadow_only"] is True

    scoreboard = router.get_scoreboard()
    assert isinstance(scoreboard, list)
