"""HybridProposalRouter for Scaffs Portfolio Allocator.

Manages persistent logging of SignalProposals, decision tracking, and shadow
book performance scoring across all 4 strategy families.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
import psycopg
from psycopg.rows import dict_row

from .proposal import SignalProposal
from src.db_dsn import resolve_dsn

logger = logging.getLogger(__name__)


def _get_default_dsn() -> str:
    return resolve_dsn()


class HybridProposalRouter:
    """Central router for storing, tracking, and scoring engine proposals."""

    def __init__(self, dsn: Optional[str] = None, allocator_version: str = "phase1_shadow_v1") -> None:
        self.dsn = dsn or _get_default_dsn()
        self.allocator_version = allocator_version

    def submit_proposal(
        self,
        proposal: SignalProposal,
        decision: str = "SHADOW_ONLY",
        reason: str = "Phase 1 explicit shadow accounting",
    ) -> Dict[str, Any]:
        """Persist a SignalProposal and log its decision in PostgreSQL.

        If the proposal's idempotency_key already exists, the insert is skipped
        and the existing record is returned (idempotent submission).
        """
        p_dict = proposal.to_dict()

        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # 1. Insert SignalProposal
                cur.execute(
                    """
                    INSERT INTO financial.signal_proposals (
                        proposal_id, idempotency_key, producer, strategy_family,
                        strategy_version, git_sha, symbol, side, generated_at,
                        valid_until, raw_score, expected_r, expected_r_lower,
                        expected_r_upper, reliability, empirical_sample_n,
                        stop_distance_pct, target_distance_pct, regime,
                        freshness_seconds, context_snapshot_id, correlation_group,
                        shadow_only, native_payload
                    ) VALUES (
                        %(proposal_id)s, %(idempotency_key)s, %(producer)s, %(strategy_family)s,
                        %(strategy_version)s, %(git_sha)s, %(symbol)s, %(side)s, %(generated_at)s,
                        %(valid_until)s, %(raw_score)s, %(expected_r)s, %(expected_r_lower)s,
                        %(expected_r_upper)s, %(reliability)s, %(empirical_sample_n)s,
                        %(stop_distance_pct)s, %(target_distance_pct)s, %(regime)s,
                        %(freshness_seconds)s, %(context_snapshot_id)s, %(correlation_group)s,
                        %(shadow_only)s, %(native_payload)s::jsonb
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                        last_seen_at = now()
                    RETURNING proposal_id, (xmin = 0) AS is_duplicate;
                    """,
                    p_dict,
                )
                res = cur.fetchone()
                proposal_id = str(res["proposal_id"])

                # 2. Insert Decision Record
                cur.execute(
                    """
                    INSERT INTO financial.signal_proposal_decisions (
                        proposal_id, decision, reason, allocator_version
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (proposal_id) DO NOTHING;
                    """,
                    (proposal_id, decision, reason, self.allocator_version),
                )

                # 3. Create initial Shadow Performance Entry (OPEN) if entry price computable
                entry_price = float(proposal.native_payload.get("entry") or proposal.native_payload.get("price") or 0.0)
                if entry_price > 0.0:
                    stop_dist = proposal.stop_distance_pct or 0.02
                    target_dist = proposal.target_distance_pct or 0.04
                    stop_price = entry_price * (1.0 - stop_dist) if proposal.side == "BUY" else entry_price * (1.0 + stop_dist)
                    target_price = entry_price * (1.0 + target_dist) if proposal.side == "BUY" else entry_price * (1.0 - target_dist)

                    cur.execute(
                        """
                        INSERT INTO financial.shadow_engine_performance (
                            proposal_id, status, entry_price, stop_price, target_price
                        ) VALUES (%s, 'OPEN', %s, %s, %s)
                        ON CONFLICT (proposal_id) DO NOTHING;
                        """,
                        (proposal_id, entry_price, stop_price, target_price),
                    )

                conn.commit()

        return {
            "proposal_id": proposal_id,
            "idempotency_key": proposal.idempotency_key,
            "producer": proposal.producer,
            "strategy_family": proposal.strategy_family,
            "decision": decision,
            "shadow_only": proposal.shadow_only,
        }

    def get_scoreboard(self) -> List[Dict[str, Any]]:
        """Query real-time shadow performance metrics grouped by engine and regime."""
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM financial.shadow_engine_scoreboard
                    ORDER BY producer, regime;
                    """
                )
                return list(cur.fetchall())
