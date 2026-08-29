"""
venue_router.py

Multi-venue execution routing across Binance, OKX, Bybit, and Gate.io.

Hard constraints this module enforces (see project architecture notes —
these are pre-existing rules, not new ones introduced here):

  1. Venue affinity per symbol until flat. A symbol with any open or pending
     exposure on venue V stays on V. Health/margin ranking never overrides
     this — an unhealthy primary venue does NOT trigger failover for a
     symbol that already has a position there. It surfaces a locked status
     for manual handling instead.
  2. No cross-venue resubmission from UNKNOWN order state. If the last known
     order status for (symbol, venue) is UNKNOWN (ambiguous ack — did it
     fill or not?), routing refuses to place the same intent on a different
     venue until that order is reconciled.
  3. Multi-venue selection is a cost/eligibility optimization, not an assumed
     source of alpha. Default policy routes 100% of an intent to the single
     best eligible venue rather than splitting size across venues.

Intuition for (1) and (2): venue affinity is a chess player committing to one
board. If that board's clock freezes mid-move, you don't get a second board —
you get one piece whose position is now unknown on the board you already
committed to. Moving it on a second board doesn't create an option, it
creates two truths that can't both be real.

This module makes ROUTING DECISIONS ONLY. It does not place orders. Given the
project's control flags (ALLOW_AUTO_EXECUTION / REQUIRE_MANUAL_APPROVAL), the
caller (signal_queue) is responsible for gating actual dispatch — a
RoutingDecision here is a recommendation + telemetry annotation, not an
execution trigger. Wire this to your real position/order-state store before
trusting VENUE_AFFINITY_LOCKED / AWAITING_RECONCILIATION behavior in
production; the interfaces below (`PositionStateProvider`,
`OrderStateProvider`) are the seams to implement against your actual DB.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol

from src.trading.risk.position_sizing import SizingResult, SizingStatus, calculate_dynamic_size

DEFAULT_MAX_U_IM = 0.15  # 15.0% safety ceiling


class OrderState(str, Enum):
    NONE = "NONE"            # no open/pending order for this (symbol, venue)
    OPEN = "OPEN"             # confirmed open position/order
    PENDING = "PENDING"       # order in flight, ack expected soon
    UNKNOWN = "UNKNOWN"       # ambiguous ack — treat as landmine, do not resubmit elsewhere


class RoutingStatus(str, Enum):
    ROUTED = "ROUTED"
    VENUE_AFFINITY_LOCKED = "VENUE_AFFINITY_LOCKED"
    AWAITING_RECONCILIATION = "AWAITING_RECONCILIATION"
    NO_ELIGIBLE_VENUE = "NO_ELIGIBLE_VENUE"
    U_IM_LIMIT_EXCEEDED = "U_IM_LIMIT_EXCEEDED"


VENUES = ("binance", "okx", "bybit", "gate")


@dataclass(frozen=True)
class VenueHealth:
    venue: str
    reachable: bool
    latency_ms: float


@dataclass(frozen=True)
class VenueMarginState:
    venue: str
    margin_balance: float
    current_u_im: float          # fraction, e.g. 0.07 == 7%
    maintenance_margin_ratio: float  # R_MM, exchange-reported; verify sign/convention against your venue adapters
    free_margin: float


@dataclass(frozen=True)
class VenueAllocationPolicy:
    max_u_im: float = DEFAULT_MAX_U_IM
    max_r_mm: float = 0.80  # placeholder ceiling — confirm against your R_MM convention before trusting this
    split_across_venues: bool = False  # default: route 100% to single best venue (see module docstring)
    latency_weight: float = 0.4
    margin_headroom_weight: float = 0.6


@dataclass(frozen=True)
class RoutingDecision:
    status: RoutingStatus
    selected_venue: Optional[str]
    target_leverage: Optional[float]
    allocated_notional: float
    u_im_telemetry: Dict[str, float]
    sizing: Optional[SizingResult]
    reason: str


class PositionStateProvider(Protocol):
    """Seam to your real position store. Must answer: does `symbol` have any
    open or pending exposure on `venue` right now?"""

    def has_exposure(self, symbol: str, venue: str) -> bool: ...

    def exposure_venue(self, symbol: str) -> Optional[str]:
        """Returns the venue currently holding exposure for `symbol`, if any
        (across ALL venues), or None if flat everywhere."""
        ...


class OrderStateProvider(Protocol):
    """Seam to your real order-state store."""

    def last_order_state(self, symbol: str, venue: str) -> OrderState: ...


@dataclass
class VenueRouter:
    policy: VenueAllocationPolicy
    position_state: PositionStateProvider
    order_state: OrderStateProvider
    health: Dict[str, VenueHealth] = field(default_factory=dict)
    margin: Dict[str, VenueMarginState] = field(default_factory=dict)

    def update_health(self, health: VenueHealth) -> None:
        self.health[health.venue] = health

    def update_margin(self, margin: VenueMarginState) -> None:
        self.margin[margin.venue] = margin

    def _is_eligible(self, venue: str) -> bool:
        h = self.health.get(venue)
        m = self.margin.get(venue)
        if h is None or m is None or not h.reachable:
            return False
        if m.current_u_im >= self.policy.max_u_im:
            return False
        if m.maintenance_margin_ratio >= self.policy.max_r_mm:
            return False
        return True

    def _rank(self, candidates: List[str]) -> List[str]:
        """Higher score = better. Normalizes latency (lower is better) and
        margin headroom (higher is better) against the candidate set only —
        this is a ranking, not an absolute score, so it's meaningless outside
        this call."""
        if not candidates:
            return []

        latencies = [self.health[v].latency_ms for v in candidates]
        headrooms = [
            self.policy.max_u_im - self.margin[v].current_u_im for v in candidates
        ]
        lat_lo, lat_hi = min(latencies), max(latencies)
        hr_lo, hr_hi = min(headrooms), max(headrooms)

        def norm(value: float, lo: float, hi: float, invert: bool = False) -> float:
            if hi == lo:
                return 1.0
            score = (value - lo) / (hi - lo)
            return (1.0 - score) if invert else score

        def score(v: str) -> float:
            lat_score = norm(self.health[v].latency_ms, lat_lo, lat_hi, invert=True)
            hr_score = norm(
                self.policy.max_u_im - self.margin[v].current_u_im, hr_lo, hr_hi
            )
            return (
                self.policy.latency_weight * lat_score
                + self.policy.margin_headroom_weight * hr_score
            )

        return sorted(candidates, key=score, reverse=True)

    def select_venue(
        self,
        symbol: str,
        target_notional: float,
        leverage: float,
    ) -> RoutingDecision:
        telemetry = {
            v: self.margin[v].current_u_im for v in self.margin
        }

        # --- Hard lock #1: venue affinity per symbol until flat ---
        locked_venue = self.position_state.exposure_venue(symbol)
        if locked_venue is not None:
            order_state = self.order_state.last_order_state(symbol, locked_venue)
            if order_state == OrderState.UNKNOWN:
                return RoutingDecision(
                    status=RoutingStatus.AWAITING_RECONCILIATION,
                    selected_venue=None,
                    target_leverage=None,
                    allocated_notional=0.0,
                    u_im_telemetry=telemetry,
                    sizing=None,
                    reason=(
                        f"{symbol} last order state on {locked_venue} is UNKNOWN; "
                        "refusing to route elsewhere until reconciled"
                    ),
                )
            # Symbol has exposure on a venue with a known state: stay put,
            # regardless of that venue's current health ranking.
            m = self.margin.get(locked_venue)
            if m is None:
                return RoutingDecision(
                    status=RoutingStatus.VENUE_AFFINITY_LOCKED,
                    selected_venue=locked_venue,
                    target_leverage=None,
                    allocated_notional=0.0,
                    u_im_telemetry=telemetry,
                    sizing=None,
                    reason=(
                        f"{symbol} is locked to {locked_venue} (existing exposure) "
                        "but no margin state is available for it"
                    ),
                )
            sizing = calculate_dynamic_size(
                margin_balance=m.margin_balance,
                current_u_im=m.current_u_im,
                max_u_im=self.policy.max_u_im,
                leverage=leverage,
                target_notional=target_notional,
            )
            if sizing.status == SizingStatus.U_IM_LIMIT_EXCEEDED:
                return RoutingDecision(
                    status=RoutingStatus.U_IM_LIMIT_EXCEEDED,
                    selected_venue=locked_venue,
                    target_leverage=leverage,
                    allocated_notional=0.0,
                    u_im_telemetry=telemetry,
                    sizing=sizing,
                    reason=sizing.reason or "U_IM limit exceeded on locked venue",
                )
            return RoutingDecision(
                status=RoutingStatus.VENUE_AFFINITY_LOCKED,
                selected_venue=locked_venue,
                target_leverage=leverage,
                allocated_notional=sizing.executed_notional,
                u_im_telemetry=telemetry,
                sizing=sizing,
                reason=f"{symbol} already has exposure on {locked_venue}; staying put",
            )

        # --- Symbol is flat everywhere: normal ranked routing applies ---
        eligible = [v for v in VENUES if self._is_eligible(v)]
        if not eligible:
            return RoutingDecision(
                status=RoutingStatus.NO_ELIGIBLE_VENUE,
                selected_venue=None,
                target_leverage=None,
                allocated_notional=0.0,
                u_im_telemetry=telemetry,
                sizing=None,
                reason="no venue passed health/U_IM/R_MM eligibility",
            )

        ranked = self._rank(eligible)
        best = ranked[0]
        m = self.margin[best]
        sizing = calculate_dynamic_size(
            margin_balance=m.margin_balance,
            current_u_im=m.current_u_im,
            max_u_im=self.policy.max_u_im,
            leverage=leverage,
            target_notional=target_notional,
        )
        if sizing.status == SizingStatus.U_IM_LIMIT_EXCEEDED:
            return RoutingDecision(
                status=RoutingStatus.U_IM_LIMIT_EXCEEDED,
                selected_venue=best,
                target_leverage=leverage,
                allocated_notional=0.0,
                u_im_telemetry=telemetry,
                sizing=sizing,
                reason=sizing.reason or "U_IM limit exceeded on best-ranked venue",
            )

        return RoutingDecision(
            status=RoutingStatus.ROUTED,
            selected_venue=best,
            target_leverage=leverage,
            allocated_notional=sizing.executed_notional,
            u_im_telemetry=telemetry,
            sizing=sizing,
            reason=f"{best} ranked highest of eligible venues {ranked}",
        )
