"""Execution provenance aggregator for Step 3 Position Risk Resolution."""
from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any, Optional

import psycopg

from src.db_dsn import resolve_dsn

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"


def _dsn(dsn: Optional[str] = None) -> str:
    return resolve_dsn(dsn, DEFAULT_DSN)


def _norm_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "")


def _entry_side_variants(position_side: str) -> list[str]:
    if position_side == "LONG":
        return ["BUY", "LONG"]
    if position_side == "SHORT":
        return ["SELL", "SHORT"]
    return ["BUY", "SELL"]


def _float_or(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def aggregate_fills(
    symbol: str,
    side: str,
    position_amt: Optional[float] = None,
    lot_precision: float = 1e-9,
    dsn: Optional[str] = None,
) -> dict[str, Any]:
    """Aggregate Scaffs fills for symbol+side and classify provenance confidence.

    Confidence:
        EXACT   - aggregate Scaffs remaining qty == reference within lot precision.
        PARTIAL - some fills exist but the qty does not reconcile.
        NONE    - no Scaffs fills for this symbol+side.

    If ``position_amt`` is omitted, the function returns PARTIAL when any fills
    are found and the aggregate Scaffs-owned quantity without a confidence label.
    """
    dsn = _dsn(dsn)
    norm_sym = _norm_symbol(symbol)
    variants = _entry_side_variants(side)
    rows: list[tuple] = []
    try:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            # UNION ALL with live_fills: real live-testnet fills (written by
            # SignalQueueManager.reconcile_pending_entries, see
            # migrations/011_limit_entry_lifecycle.sql) live in a SEPARATE
            # table from paper_trading.fills, since that table's account_id
            # FK requires a mode='paper' trading_account and a real live
            # fill doesn't belong there. Without this UNION, every live
            # position would show confidence="NONE" here (no matching rows
            # at all) and get quarantined by PositionRiskResolver regardless
            # of how correct the actual fill was.
            cur.execute(
                """
                SELECT account_id, exchange_fill_id, exchange_order_id,
                       side, quantity, price, fee, filled_at
                FROM paper_trading.fills
                WHERE symbol = %s
                  AND side = ANY(%s::text[])
                UNION ALL
                SELECT NULL::uuid AS account_id, exchange_fill_id, exchange_order_id,
                       side, quantity, price, fee, filled_at
                FROM paper_trading.live_fills
                WHERE symbol = %s
                  AND side = ANY(%s::text[])
                ORDER BY filled_at DESC;
                """,
                (norm_sym, variants, norm_sym, variants),
            )
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("Could not aggregate fills for %s %s: %s", norm_sym, side, exc)

    fills: list[dict[str, Any]] = []
    scaffs_qty = 0.0
    commission_total = 0.0
    for row in rows:
        fill = {
            "account_id": str(row[0]) if row[0] is not None else None,
            "exchange_fill_id": row[1],
            "exchange_order_id": row[2],
            "side": row[3],
            "quantity": _float_or(row[4], 0.0),
            "price": _float_or(row[5], 0.0),
            "fee": _float_or(row[6], 0.0),
            "filled_at": row[7].isoformat() if row[7] is not None else None,
        }
        fills.append(fill)
        scaffs_qty += fill["quantity"]
        commission_total += fill["fee"]

    missing_qty: Optional[float] = None
    if position_amt is not None:
        reference = abs(float(position_amt))
        missing_qty = abs(reference - scaffs_qty)
        if not rows:
            confidence = "NONE"
        elif missing_qty <= lot_precision:
            confidence = "EXACT"
        else:
            confidence = "PARTIAL"
    else:
        confidence = "PARTIAL" if rows else "NONE"

    return {
        "confidence": confidence,
        "scaffs_qty": scaffs_qty,
        "fills": fills,
        "missing_qty": missing_qty,
        "commission_total": commission_total,
    }
