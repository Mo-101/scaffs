"""SignalProposal data structure and validation for Scaffs Hybrid Portfolio Allocator.

Phase 2: observation_source is explicit (no silent default), valid_until is
entry freshness only, max_hold_seconds controls position holding period,
and legs support multi-leg proposals.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .proposal_leg import ProposalLeg

# Valid strategy families for alpha proposal engines
VALID_STRATEGY_FAMILIES = {
    "directional",       # Engine A: Idim Ikang
    "momentum",          # Engine B: Scaffs Picker
    "mean_reversion",    # Engine C: Grid Futures
    "funding_arbitrage", # Engine D: Morning Glory / Basis Arb
}

# Known producers mapping to strategy families
PRODUCER_FAMILY_MAP = {
    "idim_ikang": "directional",
    "scaffs_picker": "momentum",
    "grid_v3": "mean_reversion",
    "morning_glory": "funding_arbitrage",
}

# Valid observation sources — must be explicit at creation, never silent
VALID_OBSERVATION_SOURCES = {
    "LIVE_SHADOW",       # Genuine market-tracked proposal
    "ACCEPTANCE_TEST",   # Deliberate test fixture
    "BACKFILL",          # Historical backfill
    "SYNTHETIC",         # Synthetic/simulated
}


@dataclass
class SignalProposal:
    """Standardized SignalProposal data model emitted by independent alpha engines."""

    producer: str
    strategy_family: str
    strategy_version: str
    git_sha: str
    symbol: str
    side: str  # "BUY" or "SELL"
    generated_at: datetime
    valid_until: datetime               # Entry freshness: "too stale to ENTER after this"
    observation_source: str             # EXPLICIT — no default. Every call site must declare.
    image_digest: str = "unknown_digest"
    raw_score: Optional[float] = None
    expected_r: Optional[float] = None
    expected_r_lower: Optional[float] = None
    expected_r_upper: Optional[float] = None
    reliability: Optional[float] = None
    empirical_sample_n: int = 0
    stop_distance_pct: Optional[float] = None
    target_distance_pct: Optional[float] = None
    regime: Optional[str] = None
    freshness_seconds: Optional[float] = None
    context_snapshot_id: Optional[str] = None
    correlation_group: Optional[str] = None
    shadow_only: bool = True
    native_payload: Dict[str, Any] = field(default_factory=dict)

    # Phase 2: Holding period (separate from entry freshness)
    max_hold_seconds: Optional[int] = None          # None = engine default
    exit_policy_version: str = "v1_tp_sl_time"       # Engine-specific exit policy

    # Phase 2: Multi-leg support
    legs: List[ProposalLeg] = field(default_factory=list)

    proposal_id: uuid.UUID = field(default_factory=uuid.uuid4)
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        self.side = self.side.upper().strip()
        self.observation_source = self.observation_source.upper().strip()

        if self.strategy_family not in VALID_STRATEGY_FAMILIES:
            raise ValueError(
                f"Invalid strategy_family '{self.strategy_family}'. Must be one of {VALID_STRATEGY_FAMILIES}"
            )

        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"Invalid side '{self.side}'. Must be 'BUY' or 'SELL'.")

        if self.valid_until <= self.generated_at:
            raise ValueError("valid_until must be strictly after generated_at.")

        if self.observation_source not in VALID_OBSERVATION_SOURCES:
            raise ValueError(
                f"Invalid observation_source '{self.observation_source}'. "
                f"Must be one of {VALID_OBSERVATION_SOURCES}. "
                "This field has no default — every call site must explicitly declare the source."
            )

        if self.reliability is not None and not (0.0 <= self.reliability <= 1.0):
            raise ValueError("reliability must be between 0.0 and 1.0.")

        # Compute deterministic idempotency key if not explicitly supplied
        if not self.idempotency_key:
            payload_str = f"{self.producer}:{self.strategy_version}:{self.symbol}:{self.side}:{self.generated_at.isoformat()}"
            self.idempotency_key = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert proposal to database record dictionary."""
        return {
            "proposal_id": str(self.proposal_id),
            "idempotency_key": self.idempotency_key,
            "producer": self.producer,
            "strategy_family": self.strategy_family,
            "strategy_version": self.strategy_version,
            "git_sha": self.git_sha,
            "symbol": self.symbol,
            "side": self.side,
            "generated_at": self.generated_at,
            "valid_until": self.valid_until,
            "observation_source": self.observation_source,
            "raw_score": self.raw_score,
            "expected_r": self.expected_r,
            "expected_r_lower": self.expected_r_lower,
            "expected_r_upper": self.expected_r_upper,
            "reliability": self.reliability,
            "empirical_sample_n": self.empirical_sample_n,
            "stop_distance_pct": self.stop_distance_pct,
            "target_distance_pct": self.target_distance_pct,
            "regime": self.regime or "UNKNOWN",
            "freshness_seconds": self.freshness_seconds,
            "context_snapshot_id": self.context_snapshot_id,
            "correlation_group": self.correlation_group,
            "shadow_only": self.shadow_only,
            "native_payload": json.dumps(self.native_payload),
        }
