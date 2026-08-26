"""Steps 7-10: sync Binance Testnet fills into the canonical Scaffs futures ledger,
reconcile account state, build equity history, and calculate performance.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.trading.connectors.binance.futures_sdk import (
    BinanceFuturesClient,
    get_binance_futures_client,
)
from accounting.futures_ledger import (
    Account,
    Position,
    Side,
    close_position,
    money,
    open_position,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _load_executions_by_intent(session_dir: Path) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for rec in _load_jsonl(session_dir / "executions.jsonl"):
        intent_id = rec.get("intent_id")
        if intent_id:
            by_id[intent_id] = rec
    return by_id


def _load_fills(session_dir: Path) -> list[dict[str, Any]]:
    return _load_jsonl(session_dir / "fills.jsonl")


def _load_latest_ledger(session_dir: Path) -> tuple[Account, list[Position], Decimal] | None:
    path = session_dir / "ledger.jsonl"
    records = _load_jsonl(path)
    if not records:
        return None
    latest = records[-1]
    acct = latest.get("account", {})
    account = Account(
        available_cash=money(acct.get("available_cash", 0)),
        reserved_margin=money(acct.get("reserved_margin", 0)),
        realized_pnl=money(acct.get("realized_pnl", 0)),
        fees_paid=money(acct.get("fees_paid", 0)),
        funding_net=money(acct.get("funding_net", 0)),
    )
    positions = [
        Position(
            position_id=p.get("position_id", ""),
            symbol=p.get("symbol", ""),
            side=Side(p.get("side", "long")),
            quantity=money(p.get("quantity", 0)),
            entry_price=money(p.get("entry_price", 0)),
            leverage=money(p.get("leverage", 1)),
            margin_reserved=money(p.get("margin_reserved", 0)),
            accrued_funding=money(p.get("accrued_funding", 0)),
        )
        for p in latest.get("positions", [])
    ]
    initial_cash = Decimal(str(latest.get("initial_cash", latest["account"].get("wallet_balance", 0))))
    return account, positions, initial_cash


def _seed_account_from_exchange(client: BinanceFuturesClient) -> tuple[Account, Decimal]:
    info = client.get_account_information()
    available = money(str(info.get("availableBalance", 0)))
    wallet = money(str(info.get("totalWalletBalance", 0)))
    reserved = money(wallet - available)
    realized = money(str(info.get("totalRealizedPnl", 0)))
    account = Account(
        available_cash=available,
        reserved_margin=reserved,
        realized_pnl=realized,
        fees_paid=money(0),
        funding_net=money(0),
    )
    return account, wallet


def _to_side(side: str) -> Side:
    return Side.LONG if side.upper() == "BUY" else Side.SHORT


def _find_position_to_close(positions: list[Position], symbol: str, incoming_side: Side) -> Position | None:
    target = Side.SHORT if incoming_side is Side.LONG else Side.LONG
    for p in positions:
        if p.symbol == symbol and p.side is target:
            return p
    return None


def _sync_one_fill(
    account: Account,
    positions: list[Position],
    fill: dict[str, Any],
    executions: dict[str, dict[str, Any]],
) -> tuple[Account, list[Position], dict[str, Any]]:
    intent_id = fill.get("intent_id", "")
    symbol = fill.get("symbol", "")
    side_str = (fill.get("side") or "").upper()
    qty = money(str(fill.get("qty", 0)))
    price = money(str(fill.get("price", 0)))
    quote_qty = money(str(fill.get("quote_qty", 0)))
    commission = money(str(fill.get("commission", 0)))
    fee_rate = money(commission / quote_qty) if quote_qty > 0 else money(0)

    exec_rec = executions.get(intent_id, {})
    leverage = money(str(exec_rec.get("leverage", 1) or 1))
    fill_id = str(fill.get("fill_id", ""))
    timestamp = fill.get("timestamp", _now_iso())

    ledger_entry: dict[str, Any] = {
        "timestamp": timestamp,
        "fill_id": fill_id,
        "intent_id": intent_id,
        "symbol": symbol,
        "side": side_str,
        "qty": str(qty),
        "price": str(price),
        "quote_qty": str(quote_qty),
        "commission": str(commission),
        "fee_rate": str(fee_rate),
        "leverage": str(leverage),
    }

    incoming = _to_side(side_str)
    pos = _find_position_to_close(positions, symbol, incoming)

    if pos is None:
        result = open_position(
            account=account,
            position_id=fill_id,
            symbol=symbol,
            side=incoming,
            quantity=qty,
            execution_price=price,
            leverage=leverage,
            fee_rate=fee_rate,
        )
        account = result.account
        positions = positions + [result.position]
        ledger_entry["type"] = "open"
        ledger_entry["entry_notional"] = str(result.entry_notional)
        ledger_entry["entry_fee"] = str(result.entry_fee)
    else:
        close_qty = min(qty, pos.quantity)
        result = close_position(
            account=account,
            position=pos,
            close_quantity=close_qty,
            execution_price=price,
            fee_rate=fee_rate,
        )
        account = result.account
        if result.remaining_position is not None:
            positions = [p for p in positions if p is not pos] + [result.remaining_position]
        else:
            positions = [p for p in positions if p is not pos]
        ledger_entry["type"] = "close"
        ledger_entry["closed_quantity"] = str(result.closed_quantity)
        ledger_entry["gross_pnl"] = str(result.gross_pnl)
        ledger_entry["exit_fee"] = str(result.exit_fee)
        ledger_entry["net_pnl"] = str(result.net_pnl)
        ledger_entry["released_margin"] = str(result.released_margin)

    ledger_entry["account"] = {
        "available_cash": str(account.available_cash),
        "reserved_margin": str(account.reserved_margin),
        "realized_pnl": str(account.realized_pnl),
        "fees_paid": str(account.fees_paid),
        "funding_net": str(account.funding_net),
        "wallet_balance": str(account.wallet_balance),
    }
    ledger_entry["positions"] = [
        {
            "position_id": p.position_id,
            "symbol": p.symbol,
            "side": p.side.value,
            "quantity": str(p.quantity),
            "entry_price": str(p.entry_price),
            "leverage": str(p.leverage),
            "margin_reserved": str(p.margin_reserved),
            "accrued_funding": str(p.accrued_funding),
        }
        for p in positions
    ]

    return account, positions, ledger_entry


def sync_fills_to_ledger(
    session_dir: Path,
    client: BinanceFuturesClient | None = None,
) -> list[dict[str, Any]]:
    """Step 7: consume fills.jsonl into the canonical futures ledger."""
    client = client or get_binance_futures_client()
    state = _load_latest_ledger(session_dir)
    positions: list[Position] = []
    if state is None:
        account, initial_cash = _seed_account_from_exchange(client)
    else:
        account, positions, initial_cash = state

    executions = _load_executions_by_intent(session_dir)
    fills = _load_fills(session_dir)
    processed_fill_ids = {r.get("fill_id") for r in _load_jsonl(session_dir / "ledger.jsonl")}

    entries: list[dict[str, Any]] = []
    for fill in fills:
        fill_id = str(fill.get("fill_id", ""))
        if not fill_id or fill_id in processed_fill_ids:
            continue
        account, positions, entry = _sync_one_fill(account, positions, fill, executions)
        entry["initial_cash"] = str(initial_cash)
        _persist_jsonl(session_dir / "ledger.jsonl", entry)
        entries.append(entry)

    return entries


def build_equity_and_performance(
    session_dir: Path,
    client: BinanceFuturesClient | None = None,
) -> dict[str, Any]:
    """Steps 9-10: compute mark-to-market equity and performance from ledger state."""
    client = client or get_binance_futures_client()
    latest = _load_latest_ledger(session_dir)
    if latest is None:
        raise RuntimeError("No ledger state; run sync_fills_to_ledger first.")
    account, positions, initial_cash = latest

    unrealized = money(0)
    for p in positions:
        mark = money(str(client.get_ticker_price(p.symbol)))
        unrealized += money(p.side.sign * p.quantity * (mark - p.entry_price))

    equity = money(account.wallet_balance + unrealized)
    total_return = money(equity - initial_cash)
    total_return_pct = (
        money(total_return / initial_cash) if initial_cash > 0 else money(0)
    )

    equity_record = {
        "timestamp": _now_iso(),
        "equity": str(equity),
        "wallet_balance": str(account.wallet_balance),
        "unrealized_pnl": str(unrealized),
        "realized_pnl": str(account.realized_pnl),
        "fees_paid": str(account.fees_paid),
        "funding_net": str(account.funding_net),
        "positions": [
            {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "side": p.side.value,
                "quantity": str(p.quantity),
                "entry_price": str(p.entry_price),
                "mark_price": str(client.get_ticker_price(p.symbol)),
                "leverage": str(p.leverage),
            }
            for p in positions
        ],
    }
    _persist_jsonl(session_dir / "equity.jsonl", equity_record)

    perf_record = {
        "timestamp": _now_iso(),
        "initial_cash": str(initial_cash),
        "equity": str(equity),
        "total_return": str(total_return),
        "total_return_pct": str(total_return_pct),
        "realized_pnl": str(account.realized_pnl),
        "unrealized_pnl": str(unrealized),
        "fees_paid": str(account.fees_paid),
        "funding_net": str(account.funding_net),
        "open_positions": len(positions),
    }
    _persist_jsonl(session_dir / "performance.jsonl", perf_record)

    return {**equity_record, **{k: v for k, v in perf_record.items() if k != "timestamp"}}


def main(session_dir: Path | None = None) -> None:
    session_dir = session_dir or Path(__file__).resolve().parents[4] / "paper_sessions" / "signal_queue"
    client = get_binance_futures_client()
    entries = sync_fills_to_ledger(session_dir, client)
    logger.info("synced %s fill(s) into ledger", len(entries))
    summary = build_equity_and_performance(session_dir, client)
    logger.info("equity=%s total_return=%s (%s)", summary["equity"], summary["total_return"], summary["total_return_pct"])
