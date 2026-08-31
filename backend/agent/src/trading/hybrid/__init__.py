"""Scaffs Hybrid Portfolio Allocator Package (Phase 1)."""

from .proposal import SignalProposal, VALID_STRATEGY_FAMILIES, PRODUCER_FAMILY_MAP
from .adapters import from_idim, from_picker, from_grid, from_morning_glory
from .router import HybridProposalRouter

__all__ = [
    "SignalProposal",
    "VALID_STRATEGY_FAMILIES",
    "PRODUCER_FAMILY_MAP",
    "from_idim",
    "from_picker",
    "from_grid",
    "from_morning_glory",
    "HybridProposalRouter",
]
