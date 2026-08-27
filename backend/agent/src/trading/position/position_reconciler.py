"""Step 2 Position Reconciler for the Scaffs trading system.

Inspects live Binance USD-M Futures Testnet positions, checks whether each
has TP/SL protection, and repairs missing protection without opening new
positions.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from psycopg.types.json import Json

from src.trading.connectors.binance.futures_sdk import (
    BinanceFuturesClient,
    BinanceFuturesConfig,
    get_binance_futures_client,
)
from src.trading.position.protection_ledger import ProtectionLedger
from src.trading.position.protection_state import (
    PositionProtection,
    ProtectionBoundary,
    ProtectionStatus,
)
from src.trading.position.range_gate import evaluate_position

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"
_ORIGIN_STATUSES = ("DISPATCHED", "PROTECTION_FAILED")


def _position_side(position: dict[str, Any]) -> str:
    """Derive LONG/SHORT from a Binance USD-M positionRisk row."""
    amt = float(position.get("positionAmt", 0.0))
    if amt > 0:
        return "LONG"
    if amt < 0:
        return "SHORT"
    return "FLAT"


def _exit_order_side(position_side: str) -> str:
    return "SELL" if position_side == "LONG" else "BUY"


def _norm_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "")


def _client_algo_id(symbol: str, position_side: str, order_type: str, version: str) -> str:
    prefix = "sl" if "STOP" in order_type.upper() else "tp"
    return f"protect:{_norm_symbol(symbol)}:{position_side}:{prefix}:{version}"


def _build_version(queue_id: str, sl: Optional[float], tp: Optional[float]) -> str:
    payload = f"{queue_id}:{sl}:{tp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _inside_range(
    position_side: str,
    mark: Decimal,
    stop_loss: Optional[Decimal],
    take_profit: Optional[Decimal],
) -> bool:
    decision = evaluate_position(position_side, mark, stop_loss, take_profit)
    return decision.action == "HOLD"


def _valid_boundary(position_side: str, order_type: str, trigger: float, mark: float) -> bool:
    if "STOP" in order_type.upper():
        return trigger < mark if position_side == "LONG" else trigger > mark
    if "PROFIT" in order_type.upper():
        return trigger > mark if position_side == "LONG" else trigger < mark
    return False


def _find_origin_signal(
    cursor: Any,
    symbol: str,
    position_side: str,
) -> Optional[tuple[str, dict[str, Any]]]:
    """Return the latest DISPATCHED/PROTECTION_FAILED signal row for symbol+side."""
    variants = ("LONG", "BUY") if position_side == "LONG" else ("SHORT", "SELL")
    symbol = _norm_symbol(symbol)
    cursor.execute(
        """
        SELECT id, criteria_vector
        FROM paper_trading.signal_queue
        WHERE symbol = %s
          AND side = ANY(%s::text[])
          AND status = ANY(%s::text[])
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (symbol, list(variants), list(_ORIGIN_STATUSES)),
    )
    row = cursor.fetchone()
    if not row:
        return None
    queue_id = str(row[0])
    crit = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    return queue_id, crit


class PositionReconciler:
    """Reconcile live positions with their TP/SL protection."""

    def __init__(
        self,
        client: Optional[BinanceFuturesClient] = None,
        dsn: Optional[str] = None,
        ledger: Optional[ProtectionLedger] = None,
    ) -> None:
        self.client = client or get_binance_futures_client(BinanceFuturesConfig.from_env())
        self.dsn = dsn or os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DSN
        self.ledger = ledger or ProtectionLedger()

    def _matching_algo_orders(
        self,
        symbol: str,
        position_side: str,
        algos: list[dict[str, Any]],
    ) -> tuple[bool, bool, set[str]]:
        """Scan open algo orders for a matching SL/TP closePosition order."""
        exit_side = _exit_order_side(position_side)
        norm_sym = _norm_symbol(symbol)
        has_sl = False
        has_tp = False
        client_ids: set[str] = set()
        for o in algos:
            if _norm_symbol(str(o.get("symbol", ""))) != norm_sym:
                continue
            close_pos = str(o.get("closePosition", "")).lower()
            if close_pos not in ("true", "1"):
                continue
            order_side = str(o.get("side", "")).upper()
            order_type = str(
                o.get("type") or o.get("origType") or o.get("algoType") or ""
            ).upper()
            if order_side != exit_side:
                continue
            client_ids.add(str(o.get("clientAlgoId", "")))
            if "STOP" in order_type and "MARKET" in order_type:
                has_sl = True
            if "TAKE_PROFIT" in order_type or "PROFIT" in order_type:
                has_tp = True
        return has_sl, has_tp, client_ids

    def _repair_boundary(
        self,
        position: dict[str, Any],
        position_side: str,
        mark: float,
        order_type: str,
        trigger: float,
        version: str,
        existing_client_ids: set[str],
        dry_run: bool,
    ) -> ProtectionBoundary:
        symbol = _norm_symbol(position["symbol"])
        client_algo_id = _client_algo_id(symbol, position_side, order_type, version)
        boundary = ProtectionBoundary(
            order_type=order_type,
            trigger_price=trigger,
            client_algo_id=client_algo_id,
        )
        if client_algo_id in existing_client_ids:
            boundary.error = f"client_algo_id {client_algo_id} already exists on exchange"
            return boundary
        if not _valid_boundary(position_side, order_type, trigger, mark):
            boundary.error = (
                f"trigger {trigger} would fire immediately at mark {mark} for {position_side}"
            )
            return boundary
        if dry_run:
            return boundary
        exit_side = _exit_order_side(position_side)
        try:
            result = self.client.place_algo_order(
                symbol=symbol,
                side=exit_side,
                order_type=order_type,
                trigger_price=trigger,
                close_position=True,
                client_algo_id=client_algo_id,
            )
            boundary.placed = True
            if "client_algo_id" not in result:
                result["client_algo_id"] = client_algo_id
            logger.info("Placed %s protection for %s: %s", order_type, symbol, result)
        except Exception as exc:
            boundary.error = str(exc)
            logger.warning("Failed to place %s for %s: %s", order_type, symbol, exc)
        return boundary

    def _update_origin_criteria(
        self,
        queue_id: str,
        criteria: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        try:
            criteria["protection_reconcile"] = report
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE paper_trading.signal_queue
                    SET criteria_vector = %s
                    WHERE id = %s;
                    """,
                    (Json(criteria), queue_id),
                )
                conn.commit()
            logger.info("Updated origin criteria for queue id %s", queue_id)
        except Exception as exc:
            logger.warning("Could not persist criteria for %s: %s", queue_id, exc)

    def run(self, dry_run: bool = True) -> dict[str, Any]:
        """Inspect live positions and repair missing TP/SL protection.

        Returns a report with each position, its protection status, and any
        repairs that were attempted.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        positions = self.client.get_positions()
        algos = self.client.get_open_algo_orders()
        results: list[dict[str, Any]] = []

        for pos in positions:
            symbol = _norm_symbol(pos["symbol"])
            position_side = _position_side(pos)
            if position_side == "FLAT":
                continue

            mark = _as_float(pos.get("markPrice")) or _as_float(pos.get("entryPrice")) or 0.0
            entry = _as_float(pos.get("entryPrice"))
            has_sl, has_tp, existing_client_ids = self._matching_algo_orders(
                symbol, position_side, algos
            )

            status = ProtectionStatus.PROTECTED
            if has_sl and not has_tp:
                status = ProtectionStatus.PARTIALLY_PROTECTED
            elif not has_sl and has_tp:
                status = ProtectionStatus.PARTIALLY_PROTECTED
            elif not has_sl and not has_tp:
                status = ProtectionStatus.UNPROTECTED

            origin_queue_id: Optional[str] = None
            origin_criteria: dict[str, Any] = {}
            repairs: list[ProtectionBoundary] = []
            alert_reason: Optional[str] = None

            if status != ProtectionStatus.PROTECTED:
                try:
                    with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                        origin = _find_origin_signal(cur, symbol, position_side)
                    if origin is None:
                        status = ProtectionStatus.ALERT
                        alert_reason = (
                            f"No originating DISPATCHED/PROTECTION_FAILED signal "
                            f"for {symbol} {position_side}"
                        )
                    else:
                        origin_queue_id, origin_criteria = origin
                        stop_loss = _as_decimal(origin_criteria.get("stop_loss"))
                        take_profit = _as_decimal(origin_criteria.get("take_profit"))
                        mark_dec = _as_decimal(mark)
                        if mark_dec is not None and _inside_range(
                            position_side, mark_dec, stop_loss, take_profit
                        ):
                            version = _build_version(
                                origin_queue_id,
                                _as_float(stop_loss),
                                _as_float(take_profit),
                            )
                            missing: list[tuple[str, Optional[float]]] = []
                            if not has_sl and stop_loss is not None:
                                missing.append(("STOP_MARKET", _as_float(stop_loss)))
                            if not has_tp and take_profit is not None:
                                missing.append(("TAKE_PROFIT_MARKET", _as_float(take_profit)))

                            for order_type, trigger in missing:
                                if trigger is None:
                                    continue
                                boundary = self._repair_boundary(
                                    pos,
                                    position_side,
                                    mark,
                                    order_type,
                                    trigger,
                                    version,
                                    existing_client_ids,
                                    dry_run,
                                )
                                repairs.append(boundary)

                            if repairs:
                                any_error = any(b.error for b in repairs)
                                if any_error:
                                    status = ProtectionStatus.REPAIR_FAILED
                                elif dry_run:
                                    status = ProtectionStatus.REPAIR_PENDING
                                else:
                                    new_has_sl = has_sl or any(
                                        b.order_type == "STOP_MARKET" and not b.error
                                        for b in repairs
                                    )
                                    new_has_tp = has_tp or any(
                                        b.order_type == "TAKE_PROFIT_MARKET" and not b.error
                                        for b in repairs
                                    )
                                    if new_has_sl and new_has_tp:
                                        status = ProtectionStatus.PROTECTED
                                    else:
                                        status = ProtectionStatus.PARTIALLY_PROTECTED
                        else:
                            status = ProtectionStatus.ALERT
                            alert_reason = (
                                f"Current mark {mark} outside originating SL/TP range "
                                f"for {symbol} {position_side}"
                            )
                except Exception as exc:
                    status = ProtectionStatus.REPAIR_FAILED
                    alert_reason = f"Database or repair error: {exc}"
                    logger.warning("Reconciliation error for %s: %s", symbol, exc)

            record = PositionProtection(
                symbol=symbol,
                position_side=position_side,
                position_amt=float(pos.get("positionAmt", 0.0)),
                mark_price=mark,
                entry_price=entry,
                has_stop_loss=has_sl,
                has_take_profit=has_tp,
                status=status,
                origin_queue_id=origin_queue_id,
                origin_criteria=origin_criteria,
                repairs=repairs,
                alert_reason=alert_reason,
                dry_run=dry_run,
                note="",
            )
            results.append(record.to_dict())
            self.ledger.record(record.to_dict())

            if origin_queue_id:
                self._update_origin_criteria(
                    origin_queue_id,
                    origin_criteria,
                    {
                        "reconciled_at": timestamp,
                        "dry_run": dry_run,
                        "status": status.value,
                        "alert_reason": alert_reason,
                        "repairs": [r.to_dict() for r in repairs],
                        "has_stop_loss": has_sl,
                        "has_take_profit": has_tp,
                    },
                )

        report = {
            "run_at": timestamp,
            "dry_run": dry_run,
            "positions_count": len(results),
            "positions": results,
        }
        self.ledger.record({"summary": report})
        return report
