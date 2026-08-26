"""Canonical StrategyBinding registry for paper trading.

This module separates three distinct concepts that the previous pass
conflated:

- canonical strategy identity (UI/registry surface)
- profile/variant (e.g. 5x vs 10x grid leverage)
- execution worker_id (what actually runs in the paper engine)

The resolver is the only authoritative source for translating a canonical
strategy/profile into a worker.  No LLM output, free-text user input, or
legacy alias may bypass it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set, Tuple


@dataclass(frozen=True)
class StrategyBinding:
    canonical_id: str
    profile: Optional[str]
    worker_id: str


# Canonical strategy surface → execution worker.
# The canonical IDs here are the only ones a human/UI/registry may use.
# The worker IDs are the only values that may be written to
# paper_trading.signal_queue.target_strategy.
_BINDINGS: Dict[Tuple[str, Optional[str]], StrategyBinding] = {
    ("periodic_equal_weight_rebalance", None): StrategyBinding(
        "periodic_equal_weight_rebalance", None, "rebalance_equal_weight_v1"
    ),
    ("bounded_grid_v1", "5x"): StrategyBinding("bounded_grid_v1", "5x", "grid_futures_5x"),
    ("bounded_grid_v1", "10x"): StrategyBinding("bounded_grid_v1", "10x", "grid_futures_10x"),
    ("funding_rate_zscore", None): StrategyBinding("funding_rate_zscore", None, "morning_glory"),
}

# Convenience: full canonical identity string (e.g. "bounded_grid_v1:5x")
# and the worker allowlist used by the execution queue.
_CANONICAL_KEYS: Set[str] = set()
_WORKER_IDS: Set[str] = set()
_WORKER_TO_BINDING: Dict[str, StrategyBinding] = {}

for _k, _b in _BINDINGS.items():
    _key = _b.canonical_id if _b.profile is None else f"{_b.canonical_id}:{_b.profile}"
    _CANONICAL_KEYS.add(_key)
    _WORKER_IDS.add(_b.worker_id)
    _WORKER_TO_BINDING[_b.worker_id] = _b


def canonical_strategies() -> Set[str]:
    return set(_CANONICAL_KEYS)


def allowed_workers() -> Set[str]:
    return set(_WORKER_IDS)


def resolve_worker(canonical_id: str, profile: Optional[str] = None) -> str:
    """Return execution worker_id for a canonical strategy/profile.

    Raises ValueError for unknown canonical or profile combinations.
    """
    binding = _BINDINGS.get((canonical_id, profile))
    if binding is None:
        profile_str = f" profile={profile}" if profile is not None else ""
        raise ValueError(
            f"unsupported canonical strategy '{canonical_id}'{profile_str}; "
            f"allowed: {sorted(_CANONICAL_KEYS)}"
        )
    return binding.worker_id


def binding_for_worker(worker_id: str) -> StrategyBinding:
    """Return the canonical binding for a known worker."""
    if worker_id not in _WORKER_TO_BINDING:
        raise ValueError(f"unknown worker '{worker_id}'; allowed: {sorted(_WORKER_IDS)}")
    return _WORKER_TO_BINDING[worker_id]


def canonical_id_for_worker(worker_id: str) -> str:
    """Return the full canonical identity (e.g. 'bounded_grid_v1:5x')."""
    b = binding_for_worker(worker_id)
    return b.canonical_id if b.profile is None else f"{b.canonical_id}:{b.profile}"


def is_allowed_worker(worker_id: str) -> bool:
    return worker_id in _WORKER_IDS
