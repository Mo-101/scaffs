"""Step 3 Position Risk Resolver."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import psycopg

from src.db_dsn import resolve_dsn
from src.trading.connectors.binance.futures_sdk import (
    BinanceFuturesClient,
    BinanceFuturesConfig,
    get_binance_futures_client,
)
from src.trading.position.provenance import aggregate_fills

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"
_ORIGIN_STATUSES = ("DISPATCHED", "PARTIALLY_FILLED", "PROTECTED", "PROTECTION_FAILED")


class ResolutionAction(str, Enum):
    """Canonical Step 3 resolution actions."""

    HOLD = "HOLD"
    PROTECT = "PROTECT"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    QUARANTINE = "QUARANTINE"


@dataclass
class Resolution:
    """Full result of resolving one Binance position."""

    action: ResolutionAction
    origin_queue_id: Optional[str] = None
    origin_criteria: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    effective_stop: Optional[float] = None
    mark_price: Optional[float] = None
    has_stop_loss: bool = False
    has_take_profit: bool = False


def _norm_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "")


def _position_side(position: dict[str, Any]) -> str:
    amt = float(position.get("positionAmt", 0.0))
    if amt > 0:
        return "LONG"
    if amt < 0:
        return "SHORT"
    return "FLAT"


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


class PositionRiskResolver:
    """Resolve a live Binance position into a deterministic Step 3 action."""

    def __init__(
        self,
        client: Optional[BinanceFuturesClient] = None,
        dsn: Optional[str] = None,
    ) -> None:
        self.client = client
        self.dsn = resolve_dsn(dsn, DEFAULT_DSN)

    def _find_origin_signal(
        self,
        symbol: str,
        position_side: str,
    ) -> Optional[tuple[str, dict[str, Any]]]:
        """Return the latest DISPATCHED/PROTECTION_FAILED signal for symbol+side."""
        variants = ("LONG", "BUY") if position_side == "LONG" else ("SHORT", "SELL")
        norm_sym = _norm_symbol(symbol)
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, criteria_vector
                FROM paper_trading.signal_queue
                WHERE symbol = %s
                  AND side = ANY(%s::text[])
                  AND status = ANY(%s::text[])
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (norm_sym, list(variants), list(_ORIGIN_STATUSES)),
            )
            row = cur.fetchone()
            if not row:
                return None
            queue_id = str(row[0])
            crit = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
            return queue_id, crit

    def _matching_algo_orders(
        self,
        symbol: str,
        position_side: str,
        algos: list[dict[str, Any]],
    ) -> tuple[bool, bool]:
        """Scan open algo orders for a matching SL/TP closePosition order."""
        exit_side = "SELL" if position_side == "LONG" else "BUY"
        norm_sym = _norm_symbol(symbol)
        has_sl = False
        has_tp = False
        for o in algos:
            if _norm_symbol(str(o.get("symbol", ""))) != norm_sym:
                continue
            close_pos = str(o.get("closePosition", "")).lower()
            if close_pos not in ("true", "1"):
                continue
            if str(o.get("side", "")).upper() != exit_side:
                continue
            order_type = str(
                o.get("orderType")
                or o.get("type")
                or o.get("origType")
                or o.get("algoType")
                or ""
            ).upper()
            if "STOP" in order_type and "MARKET" in order_type:
                has_sl = True
            if "TAKE_PROFIT" in order_type or "PROFIT" in order_type:
                has_tp = True
        return has_sl, has_tp

    def resolve_full(
        self,
        position: dict[str, Any],
        algos: Optional[list[dict[str, Any]]] = None,
    ) -> Resolution:
        """Resolve one position and return full context."""
        symbol = _norm_symbol(position.get("symbol", ""))
        position_side = _position_side(position)
        if position_side == "FLAT":
            return Resolution(action=ResolutionAction.HOLD)

        position_amt = abs(float(position.get("positionAmt", 0.0)))
        mark = _as_float(position.get("markPrice")) or _as_float(position.get("entryPrice")) or 0.0

        lot_precision = 1e-9
        if self.client is not None:
            try:
                prec = self.client.get_quantity_precision(symbol)
                if prec is not None and prec >= 0:
                    lot_precision = 10 ** -prec
            except Exception:
                pass

        provenance = aggregate_fills(
            symbol,
            position_side,
            position_amt=position_amt,
            lot_precision=lot_precision,
            dsn=self.dsn,
        )
        if provenance["confidence"] != "EXACT":
            return Resolution(
                action=ResolutionAction.QUARANTINE,
                provenance=provenance,
            )

        origin = self._find_origin_signal(symbol, position_side)
        if origin is None:
            return Resolution(
                action=ResolutionAction.QUARANTINE,
                provenance=provenance,
            )

        queue_id, criteria = origin
        sl = _as_float(criteria.get("stop_loss"))
        tp = _as_float(criteria.get("take_profit"))

        if algos is None and self.client is not None:
            try:
                algos = self.client.get_open_algo_orders(symbol=symbol)
            except Exception:
                algos = []

        has_sl = False
        has_tp = False
        if algos is not None:
            has_sl, has_tp = self._matching_algo_orders(symbol, position_side, algos)

        if sl is not None:
            if position_side == "LONG" and mark <= sl:
                return Resolution(
                    action=ResolutionAction.CLOSE_LONG,
                    origin_queue_id=queue_id,
                    origin_criteria=criteria,
                    provenance=provenance,
                    stop_loss=sl,
                    take_profit=tp,
                    effective_stop=sl,
                    mark_price=mark,
                    has_stop_loss=has_sl,
                    has_take_profit=has_tp,
                )
            if position_side == "SHORT" and mark >= sl:
                return Resolution(
                    action=ResolutionAction.CLOSE_SHORT,
                    origin_queue_id=queue_id,
                    origin_criteria=criteria,
                    provenance=provenance,
                    stop_loss=sl,
                    take_profit=tp,
                    effective_stop=sl,
                    mark_price=mark,
                    has_stop_loss=has_sl,
                    has_take_profit=has_tp,
                )

        # No protective boundaries requested -> nothing to attach.
        if sl is None and tp is None:
            return Resolution(
                action=ResolutionAction.HOLD,
                origin_queue_id=queue_id,
                origin_criteria=criteria,
                provenance=provenance,
                stop_loss=sl,
                take_profit=tp,
                mark_price=mark,
                has_stop_loss=has_sl,
                has_take_profit=has_tp,
            )

        if has_sl and has_tp:
            return Resolution(
                action=ResolutionAction.HOLD,
                origin_queue_id=queue_id,
                origin_criteria=criteria,
                provenance=provenance,
                stop_loss=sl,
                take_profit=tp,
                mark_price=mark,
                has_stop_loss=has_sl,
                has_take_profit=has_tp,
            )

        return Resolution(
            action=ResolutionAction.PROTECT,
            origin_queue_id=queue_id,
            origin_criteria=criteria,
            provenance=provenance,
            stop_loss=sl,
            take_profit=tp,
            mark_price=mark,
            has_stop_loss=has_sl,
            has_take_profit=has_tp,
        )

    def resolve(
        self,
        position: dict[str, Any],
        algos: Optional[list[dict[str, Any]]] = None,
    ) -> ResolutionAction:
        """Resolve one position and return the canonical action."""
        return self.resolve_full(position, algos=algos).action
