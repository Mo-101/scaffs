"""ProposalLeg data structure for multi-leg shadow accounting.

Idim/Picker → 1 leg (ENTRY).
Morning Glory → 2+ legs (SPOT_HEDGE + PERP_FUNDING_LEG).
Grid → N legs (GRID_LEVEL), with a derived net campaign view in SQL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# Valid leg roles describing the purpose of each leg within a proposal
VALID_LEG_ROLES = {
    "ENTRY",              # Standard single-leg entry (Idim, Picker)
    "HEDGE",              # Hedging leg
    "GRID_LEVEL",         # Individual grid fill/level
    "FUNDING_LEG",        # Generic funding-related leg
    "EXIT",               # Explicit exit leg
    "SPOT_HEDGE",         # Morning Glory: spot market hedge
    "PERP_FUNDING_LEG",   # Morning Glory: perpetual funding position
}

# Valid exit reasons — engine-specific, never forced into TP/SL/TIME
VALID_EXIT_REASONS = {
    "TP",                 # Take-profit hit
    "SL",                 # Stop-loss hit
    "TIME",               # Max hold expired
    "LIQUIDATION",        # Position liquidated
    "FUNDING_EXIT",       # Funding rate inverted (Morning Glory)
    "GRID_COMPLETE",      # All grid levels filled/complete (Grid)
    "ARBITRAGE_CLOSE",    # Basis converged (Morning Glory)
    "INVALIDATED",        # Proposal invalidated before resolution
}


@dataclass
class ProposalLeg:
    """One leg of a multi-leg shadow proposal."""

    leg_index: int
    instrument: str          # e.g. BTCUSDT, ETHUSDT
    side: str                # BUY or SELL
    leg_role: str = "ENTRY"  # from VALID_LEG_ROLES

    venue: str = "binance_futures"
    entry_price: Optional[float] = None
    quantity: Optional[float] = None
    notional_usd: Optional[float] = None
    fee_model: str = "maker_taker"
    funding_model: Optional[str] = None   # 'perpetual_funding' for perps, None for spot

    leg_id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        self.instrument = self.instrument.upper().strip()
        self.side = self.side.upper().strip()
        self.leg_role = self.leg_role.upper().strip()

        if self.side not in {"BUY", "SELL"}:
            raise ValueError(f"Invalid leg side '{self.side}'. Must be 'BUY' or 'SELL'.")
        if self.leg_role not in VALID_LEG_ROLES:
            raise ValueError(
                f"Invalid leg_role '{self.leg_role}'. Must be one of {VALID_LEG_ROLES}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert leg to database record dictionary."""
        return {
            "leg_id": str(self.leg_id),
            "leg_index": self.leg_index,
            "leg_role": self.leg_role,
            "venue": self.venue,
            "instrument": self.instrument,
            "side": self.side,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "notional_usd": self.notional_usd,
            "fee_model": self.fee_model,
            "funding_model": self.funding_model,
        }
