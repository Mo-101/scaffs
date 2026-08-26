"""Step 6: reconcile Scaffs execution records with live Binance order state and fills."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.trading.trade_intent import ExecutionResult
from src.trading.connectors.binance.futures_sdk import BinanceFuturesClient

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_latest_executions(executions_path: Path) -> dict[str, dict[str, Any]]:
    """Return the most recent execution record for each intent_id."""
    latest: dict[str, dict[str, Any]] = {}
    if not executions_path.exists():
        return latest
    for line in executions_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        intent_id = record.get("intent_id")
        if intent_id:
            latest[intent_id] = record
    return latest


def _binance_status_to_scaffs(status: str | None) -> str:
    mapping = {
        "NEW": "SUBMITTED",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "FILLED": "FILLED",
        "CANCELED": "CANCELED",
        "EXPIRED": "EXPIRED",
        "REJECTED": "REJECTED",
    }
    return mapping.get(status or "", "UNKNOWN")


def _persist_fill(session_dir: Path, intent_id: str, fill: dict[str, Any]) -> None:
    ts_ms = int(fill.get("time", 0))
    timestamp = (
        datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
        if ts_ms
        else _now_iso()
    )
    record = {
        "intent_id": intent_id,
        "exchange_order_id": str(fill.get("orderId", "")),
        "symbol": fill.get("symbol"),
        "fill_id": str(fill.get("id", "")),
        "price": float(fill.get("price", 0.0) or 0.0),
        "qty": float(fill.get("qty", 0.0) or 0.0),
        "quote_qty": float(fill.get("quoteQty", 0.0) or 0.0),
        "commission": float(fill.get("commission", 0.0) or 0.0),
        "commission_asset": fill.get("commissionAsset"),
        "realized_pnl": float(fill.get("realizedPnl", 0.0) or 0.0),
        "side": fill.get("side"),
        "timestamp": timestamp,
        "recorded_at": _now_iso(),
    }
    _persist_jsonl(session_dir / "fills.jsonl", record)


def _build_updated_execution(
    record: dict[str, Any], order: dict[str, Any], new_status: str, fills: list[dict[str, Any]]
) -> dict[str, Any]:
    avg_px = float(order.get("avgPrice", 0.0) or 0.0)
    filled_qty = float(order.get("executedQty", 0.0) or 0.0)
    realized = sum(float(f.get("realizedPnl", 0.0) or 0.0) for f in fills)
    commission = sum(float(f.get("commission", 0.0) or 0.0) for f in fills)
    base = {**record}
    base.pop("recorded_at", None)
    base["status"] = new_status
    base["filled_price"] = avg_px
    base["filled_qty"] = filled_qty
    base["realized_pnl"] = realized
    base["commission"] = commission
    base["raw_status"] = order
    base["submitted_at"] = base.get("submitted_at") or _now_iso()
    return {k: v for k, v in base.items() if k in ExecutionResult.__dataclass_fields__}


def reconcile_orders(session_dir: Path, client: BinanceFuturesClient) -> list[ExecutionResult]:
    """Poll the exchange for all SUBMITTED executions and append reconciled state."""
    executions_path = session_dir / "executions.jsonl"
    latest_by_intent = _load_latest_executions(executions_path)
    results: list[ExecutionResult] = []

    for intent_id, record in latest_by_intent.items():
        if record.get("status") != "SUBMITTED":
            continue
        exchange_order_id = record.get("exchange_order_id")
        if not exchange_order_id:
            continue
        symbol = (record.get("raw_status") or {}).get("order", {}).get("symbol")
        if not symbol:
            continue

        try:
            order = client.get_order(symbol, order_id=int(exchange_order_id))
        except Exception as exc:
            logger.warning("Failed to reconcile order %s: %s", exchange_order_id, exc)
            continue

        new_status = _binance_status_to_scaffs(order.get("status"))
        if new_status == "SUBMITTED":
            # No terminal state change yet.
            continue

        try:
            fills = client.get_order_trades(symbol, int(exchange_order_id))
        except Exception as exc:
            logger.warning("Failed to fetch fills for %s: %s", exchange_order_id, exc)
            fills = []

        for fill in fills:
            _persist_fill(session_dir, intent_id, fill)

        updated = _build_updated_execution(record, order, new_status, fills)
        _persist_jsonl(executions_path, {**updated, "recorded_at": _now_iso()})
        results.append(ExecutionResult(**updated))

    return results
