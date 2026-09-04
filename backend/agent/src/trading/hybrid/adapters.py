"""Engine adapters converting native strategy outputs into standardized SignalProposals."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .proposal import SignalProposal

def get_git_sha() -> str:
    """Resolve current git SHA for provenance tracking."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return os.getenv("GIT_SHA", "unknown_sha")


def get_container_image_digest() -> str:
    """Resolve immutable container image digest for deployment provenance."""
    return os.getenv("CONTAINER_IMAGE_DIGEST") or os.getenv("IMAGE_DIGEST") or "sha256:local_dev_build"


def from_idim(
    signal: Dict[str, Any],
    strategy_version: str = "idim_v1",
    git_sha: Optional[str] = None,
    ttl_seconds: int = 900,
) -> SignalProposal:
    """Engine A Adapter: Convert Idim Ikang directional market intelligence signal."""
    now = datetime.now(timezone.utc)
    ts_val = signal.get("ts") or signal.get("generated_at")
    if isinstance(ts_val, str):
        try:
            generated_at = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        except ValueError:
            generated_at = now
    elif isinstance(ts_val, datetime):
        generated_at = ts_val
    else:
        generated_at = now

    valid_until = generated_at + timedelta(seconds=ttl_seconds)
    pair = str(signal.get("pair") or signal.get("symbol") or "BTC-USDT").replace("_", "-").upper()
    side = str(signal.get("side") or "BUY").upper()
    score = float(signal.get("score") or signal.get("raw_score") or 50.0)

    # Estimate stop distance / target distance from entry if present
    entry = float(signal.get("entry") or 0.0)
    stop = float(signal.get("stop_loss") or 0.0)
    target = float(signal.get("take_profit") or 0.0)

    stop_pct = abs(entry - stop) / entry if entry > 0 and stop > 0 else 0.02
    target_pct = abs(target - entry) / entry if entry > 0 and target > 0 else 0.04
    expected_r = target_pct / stop_pct if stop_pct > 0 else 2.0

    return SignalProposal(
        producer="idim_ikang",
        strategy_family="directional",
        strategy_version=strategy_version,
        git_sha=git_sha or get_git_sha(),
        symbol=pair,
        side=side,
        generated_at=generated_at,
        valid_until=valid_until,
        raw_score=score,
        expected_r=expected_r,
        stop_distance_pct=stop_pct,
        target_distance_pct=target_pct,
        regime=str(signal.get("regime") or signal.get("btc_regime") or "UNKNOWN"),
        freshness_seconds=max(0.0, (now - generated_at).total_seconds()),
        shadow_only=True,
        native_payload=signal,
    )


def from_sigmalui(
    signal: Dict[str, Any],
    strategy_version: str = "sigmalui_v1",
    git_sha: Optional[str] = None,
    ttl_seconds: int = 600,
) -> SignalProposal:
    """Engine S Adapter: Convert SigmaLui Soul Giver directional signal.

    SigmaLui payloads use asset/action/entryPrice/takeProfit1/stopLoss/topisScore
    keys. Normalizes them into the canonical SignalProposal schema.
    """
    now = datetime.now(timezone.utc)
    ts_val = signal.get("timestamp") or signal.get("ts") or signal.get("created_at") or signal.get("createdAt")
    if isinstance(ts_val, str):
        try:
            generated_at = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
        except ValueError:
            generated_at = now
    elif isinstance(ts_val, datetime):
        generated_at = ts_val
    else:
        generated_at = now

    valid_until = generated_at + timedelta(seconds=ttl_seconds)
    pair = str(signal.get("futuresPair") or signal.get("asset") or signal.get("symbol") or "BTC-USDT")
    pair = pair.replace("/", "").replace(".", "").replace("-", "")
    # Drop common perpetual suffixes that are not part of Binance symbols.
    for suffix in ("P", "PERP"):
        if pair.upper().endswith(suffix):
            pair = pair[: -len(suffix)]
    pair = pair.upper()
    side = str(signal.get("side") or signal.get("action") or "BUY").upper()
    action = side
    if action in ("STRONG_BUY", "BUY"):
        side = "BUY"
    elif action in ("STRONG_SELL", "SELL"):
        side = "SELL"

    score = float(signal.get("raw_score") or signal.get("score") or signal.get("topsisScore") or signal.get("confidencePct") or 50.0)
    if score <= 1.0 and ("topsisScore" in signal or "topsis_score" in signal.get("criteria", {})):
        score = score * 100.0

    crit = signal.get("criteria") or signal
    entry = float(
        signal.get("entry") or signal.get("entryPrice") or signal.get("price")
        or crit.get("entry") or crit.get("entryPrice") or 0.0
    )
    stop = float(
        signal.get("stop_loss") or signal.get("stopLoss") or signal.get("sl")
        or crit.get("stop_loss") or crit.get("stopLoss") or 0.0
    )
    target = float(
        signal.get("take_profit") or signal.get("takeProfit1") or signal.get("target1")
        or crit.get("take_profit") or crit.get("takeProfit1") or 0.0
    )

    stop_pct = abs(entry - stop) / entry if entry > 0 and stop > 0 else 0.012
    target_pct = abs(target - entry) / entry if entry > 0 and target > 0 else 0.024
    expected_r = target_pct / stop_pct if stop_pct > 0 else 2.0

    return SignalProposal(
        producer="sigmalui",
        strategy_family="directional",
        strategy_version=strategy_version,
        git_sha=git_sha or get_git_sha(),
        symbol=pair,
        side=side,
        generated_at=generated_at,
        valid_until=valid_until,
        observation_source="LIVE_SHADOW",
        raw_score=score,
        expected_r=expected_r,
        stop_distance_pct=stop_pct,
        target_distance_pct=target_pct,
        regime=str(signal.get("regime") or signal.get("marketRegime") or "UNKNOWN"),
        freshness_seconds=max(0.0, (now - generated_at).total_seconds()),
        shadow_only=True,
        native_payload=signal,
    )


def from_picker(
    signal: Dict[str, Any],
    strategy_version: str = "picker_v2",
    git_sha: Optional[str] = None,
    ttl_seconds: int = 600,
) -> SignalProposal:
    """Engine B Adapter: Convert Scaffs Picker short-horizon momentum/breakout signal."""
    now = datetime.now(timezone.utc)
    generated_at = now
    valid_until = generated_at + timedelta(seconds=ttl_seconds)

    symbol = str(signal.get("symbol") or signal.get("pair") or "BTC-USDT").upper()
    side = str(signal.get("side") or "BUY").upper()
    score = float(signal.get("score") or signal.get("momentum_score") or 60.0)

    return SignalProposal(
        producer="scaffs_picker",
        strategy_family="momentum",
        strategy_version=strategy_version,
        git_sha=git_sha or get_git_sha(),
        symbol=symbol,
        side=side,
        generated_at=generated_at,
        valid_until=valid_until,
        raw_score=score,
        expected_r=1.8,
        stop_distance_pct=float(signal.get("stop_pct") or 0.015),
        target_distance_pct=float(signal.get("target_pct") or 0.027),
        regime=str(signal.get("regime") or "TRENDING"),
        freshness_seconds=0.0,
        shadow_only=True,
        native_payload=signal,
    )


def from_grid(
    grid_event: Dict[str, Any],
    strategy_version: str = "grid_futures_v3",
    git_sha: Optional[str] = None,
    ttl_seconds: int = 300,
) -> SignalProposal:
    """Engine C Adapter: Convert Grid Futures range-bound mean-reversion proposal."""
    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(seconds=ttl_seconds)

    symbol = str(grid_event.get("symbol") or "ETH-USDT").upper()
    side = str(grid_event.get("side") or "BUY").upper()

    return SignalProposal(
        producer="grid_v3",
        strategy_family="mean_reversion",
        strategy_version=strategy_version,
        git_sha=git_sha or get_git_sha(),
        symbol=symbol,
        side=side,
        generated_at=now,
        valid_until=valid_until,
        raw_score=float(grid_event.get("grid_confidence") or 70.0),
        expected_r=1.2,
        stop_distance_pct=float(grid_event.get("grid_spacing_pct") or 0.01),
        target_distance_pct=float(grid_event.get("grid_spacing_pct") or 0.01),
        regime="RANGING",
        freshness_seconds=0.0,
        shadow_only=True,
        native_payload=grid_event,
    )


def from_morning_glory(
    funding_event: Dict[str, Any],
    strategy_version: str = "morning_glory_v1",
    git_sha: Optional[str] = None,
    ttl_seconds: int = 1800,
) -> SignalProposal:
    """Engine D Adapter: Convert Morning Glory funding rate & basis arbitrage proposal."""
    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(seconds=ttl_seconds)

    symbol = str(funding_event.get("symbol") or "BTC-USDT").upper()
    side = str(funding_event.get("side") or "BUY").upper()
    annualized_yield = float(funding_event.get("annualized_yield_pct") or 15.0)

    return SignalProposal(
        producer="morning_glory",
        strategy_family="funding_arbitrage",
        strategy_version=strategy_version,
        git_sha=git_sha or get_git_sha(),
        symbol=symbol,
        side=side,
        generated_at=now,
        valid_until=valid_until,
        raw_score=min(100.0, annualized_yield * 2.0),
        expected_r=2.5,
        stop_distance_pct=0.008,
        target_distance_pct=0.020,
        regime="NEUTRAL_YIELD",
        freshness_seconds=0.0,
        shadow_only=True,
        native_payload=funding_event,
    )
