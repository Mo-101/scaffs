"""Idempotent reduce-only position close for Step 3."""
from __future__ import annotations

import logging
import os
import time
from decimal import Decimal
from typing import Any, Optional

import psycopg

from src.trading.connectors.binance.futures_sdk import (
    BinanceFuturesClient,
    BinanceFuturesConfig,
    get_binance_futures_client,
    require_binance_testnet_env,
)

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"


class PositionCloseError(RuntimeError):
    """Raised when a reduce-only close cannot be safely submitted."""


def _dsn(dsn: Optional[str] = None) -> str:
    return dsn or os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DSN


def _norm_symbol(symbol: str) -> str:
    return symbol.upper().replace("-", "").replace("/", "")


def _float_or(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _update_reservation(
    dsn: str,
    client_order_id: str,
    status: str,
    binance_order_id: Optional[str] = None,
) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE paper_trading.close_reservations
            SET status = %s,
                binance_order_id = %s,
                updated_at = NOW()
            WHERE client_order_id = %s;
            """,
            (status, binance_order_id, client_order_id),
        )
        conn.commit()


def _build_result(
    client_order_id: str,
    status: str,
    order: Optional[dict[str, Any]] = None,
    skipped: bool = False,
) -> dict[str, Any]:
    return {
        "client_order_id": client_order_id,
        "status": status,
        "order": order or {},
        "skipped": skipped,
    }


def _wait_for_final(
    client: BinanceFuturesClient,
    symbol: str,
    client_order_id: str,
    order_id: Any,
    max_attempts: int = 5,
    sleep_seconds: float = 2.0,
) -> Optional[dict[str, Any]]:
    for attempt in range(max_attempts):
        try:
            order = client.get_order(symbol, client_order_id=client_order_id)
            if not order:
                break
            st = (order.get("status") or "").upper()
            if st in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                return order
            if st in ("NEW", "PARTIALLY_FILLED"):
                if attempt < max_attempts - 1:
                    time.sleep(sleep_seconds)
                continue
            # Unknown/terminal-ish status
            return order
        except Exception as exc:
            logger.warning(
                "Could not poll close order %s (%s): %s",
                client_order_id,
                order_id,
                exc,
            )
            break
    return None


def _cancel_orphan_algos(
    client: BinanceFuturesClient,
    symbol: str,
) -> None:
    """Cancel any TP/SL closePosition algo orders after the position is flat."""
    try:
        algos = client.get_open_algo_orders(symbol=symbol)
        for o in algos:
            if str(o.get("closePosition", "")).lower() not in ("true", "1"):
                continue
            algo_id = o.get("algoId") or o.get("orderId")
            if not algo_id:
                continue
            try:
                client._request(
                    "DELETE",
                    "/fapi/v1/algoOrder",
                    params={"symbol": _norm_symbol(symbol), "algoId": str(algo_id)},
                    signed=True,
                )
                logger.info("Canceled orphan algo order %s for %s", algo_id, symbol)
            except Exception as exc:
                logger.warning(
                    "Could not cancel orphan algo order %s for %s: %s",
                    algo_id,
                    symbol,
                    exc,
                )
    except Exception as exc:
        logger.warning("Could not fetch orphan algo orders for %s: %s", symbol, exc)


def _persist_closed_position(
    dsn: str,
    symbol: str,
    side: str,
    entry_price: Optional[float],
    exit_price: float,
    quantity: float,
    realized_pnl: float,
    commission: float,
) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO paper_trading.closed_positions (
                symbol, side, entry_price, exit_price, quantity,
                realized_pnl, commission, closed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());
            """,
            (
                _norm_symbol(symbol),
                side,
                entry_price,
                exit_price,
                quantity,
                realized_pnl,
                commission,
            ),
        )
        conn.commit()


def _finalize_close(
    symbol: str,
    client: BinanceFuturesClient,
    order: dict[str, Any],
    client_order_id: str,
    dsn: str,
    side: str,
    entry_price: Optional[float],
) -> None:
    """Extract realized PnL/commission, persist closure, and cancel orphan algos."""
    order_id = order.get("orderId")
    if not order_id:
        return

    realized_pnl = 0.0
    commission = 0.0
    qty = 0.0
    quote = 0.0
    try:
        trades = client.get_order_trades(symbol, order_id=int(order_id))
        for t in trades:
            realized_pnl += _float_or(t.get("realizedPnl"), 0.0)
            commission += _float_or(t.get("commission"), 0.0)
            qty += _float_or(t.get("qty"), 0.0)
            quote += _float_or(t.get("quoteQty"), 0.0)
    except Exception as exc:
        logger.warning(
            "Could not fetch close trades for %s %s: %s",
            client_order_id,
            order_id,
            exc,
        )

    exit_price = quote / qty if qty > 0 else _float_or(order.get("avgPrice"), 0.0)

    _persist_closed_position(
        dsn,
        _norm_symbol(symbol),
        side,
        entry_price,
        exit_price,
        qty,
        realized_pnl,
        commission,
    )

    # Only cancel orphan TP/SL if the position is actually flat.
    try:
        positions = client.get_positions(symbol=symbol)
        flat = not positions or all(
            float(p.get("positionAmt", 0.0)) == 0.0 for p in positions
        )
        if flat:
            _cancel_orphan_algos(client, symbol)
    except Exception as exc:
        logger.warning("Could not verify flat position for %s: %s", symbol, exc)


def reduce_only_close(
    symbol: str,
    side: str,
    quantity: float,
    client_order_id: str,
    client: Optional[BinanceFuturesClient] = None,
    dsn: Optional[str] = None,
    mark_price: Optional[float] = None,
    entry_price: Optional[float] = None,
) -> dict[str, Any]:
    """Place a deterministic, reduce-only market close and reconcile with Binance.

    The exit-risk gate checks:
        - TRADING_ENV is binance_testnet;
        - the exchange still reports an open position of the same symbol/side;
        - requested quantity does not exceed the authoritative Binance position;
        - the order is submitted with reduceOnly=true;
        - a persistent reservation prevents duplicate submission after restart.
    """
    require_binance_testnet_env()
    client = client or get_binance_futures_client(BinanceFuturesConfig.from_env())
    dsn = _dsn(dsn)
    formatted_symbol = _norm_symbol(symbol)

    # Authoritative Binance position assertion
    positions = client.get_positions(symbol=formatted_symbol)
    if not positions:
        raise PositionCloseError(f"No open Binance position for {formatted_symbol}")

    pos = positions[0]
    position_amt = float(pos.get("positionAmt", 0.0))
    if position_amt == 0.0:
        raise PositionCloseError(f"Binance position for {formatted_symbol} is already flat")
    if side == "LONG" and position_amt <= 0.0:
        raise PositionCloseError(
            f"Expected LONG position for {formatted_symbol}, got {position_amt}"
        )
    if side == "SHORT" and position_amt >= 0.0:
        raise PositionCloseError(
            f"Expected SHORT position for {formatted_symbol}, got {position_amt}"
        )

    binance_qty = abs(position_amt)
    if quantity > binance_qty:
        raise PositionCloseError(
            f"Close quantity {quantity} exceeds Binance position {binance_qty}"
        )

    # Idempotent reservation before submission
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO paper_trading.close_reservations (
                client_order_id, symbol, side, quantity, status
            ) VALUES (%s, %s, %s, %s, 'PENDING')
            ON CONFLICT (client_order_id) DO NOTHING;
            """,
            (client_order_id, formatted_symbol, side, quantity),
        )
        conn.commit()
        cur.execute(
            """
            SELECT id, status, binance_order_id
            FROM paper_trading.close_reservations
            WHERE client_order_id = %s;
            """,
            (client_order_id,),
        )
        row = cur.fetchone()
        existing_status = row[1] if row else None

    if existing_status in ("FILLED", "CANCELLED", "REJECTED"):
        logger.info(
            "Close reservation %s already terminal (%s); skipping.",
            client_order_id,
            existing_status,
        )
        return _build_result(client_order_id, existing_status, skipped=True)

    # Exchange reconciliation before placement avoids duplicates after restart.
    try:
        existing_order = client.get_order(
            formatted_symbol, client_order_id=client_order_id
        )
        if existing_order and existing_order.get("orderId"):
            st = (existing_order.get("status") or "").upper()
            if st == "FILLED":
                _update_reservation(
                    dsn,
                    client_order_id,
                    "FILLED",
                    str(existing_order.get("orderId")),
                )
                _finalize_close(
                    formatted_symbol,
                    client,
                    existing_order,
                    client_order_id,
                    dsn,
                    side,
                    entry_price,
                )
                return _build_result(client_order_id, "FILLED", existing_order)
            if st in ("CANCELED", "EXPIRED", "REJECTED"):
                _update_reservation(
                    dsn,
                    client_order_id,
                    "CANCELLED",
                    str(existing_order.get("orderId")),
                )
                return _build_result(client_order_id, "CANCELLED", existing_order)
    except Exception:
        pass  # order does not exist; proceed with placement

    exit_side = "SELL" if side == "LONG" else "BUY"
    result = client.place_order(
        symbol=formatted_symbol,
        side=exit_side,
        order_type="MARKET",
        quantity=quantity,
        reduce_only=True,
        client_order_id=client_order_id,
    )
    raw_order = result.get("order", {}) if isinstance(result, dict) else {}
    order_id = raw_order.get("orderId")
    _update_reservation(dsn, client_order_id, "SUBMITTED", str(order_id) if order_id else None)

    final_order = _wait_for_final(
        client,
        formatted_symbol,
        client_order_id,
        order_id,
    )
    if not final_order:
        raise PositionCloseError(
            f"Could not confirm close order {client_order_id} status"
        )

    final_status = (final_order.get("status") or "").upper()
    if final_status == "FILLED":
        _update_reservation(
            dsn,
            client_order_id,
            "FILLED",
            str(final_order.get("orderId")),
        )
        _finalize_close(
            formatted_symbol,
            client,
            final_order,
            client_order_id,
            dsn,
            side,
            entry_price,
        )
        return _build_result(client_order_id, "FILLED", final_order)

    if final_status in ("CANCELED", "EXPIRED", "REJECTED"):
        _update_reservation(
            dsn,
            client_order_id,
            "CANCELLED",
            str(final_order.get("orderId")),
        )
        return _build_result(client_order_id, "CANCELLED", final_order)

    raise PositionCloseError(
        f"Close order {client_order_id} in unexpected status {final_status}"
    )
