#!/usr/bin/env python3
"""The single session contract the dashboard is allowed to read.

``build_session_dto`` reads one ``futures_paper_engine`` session directory --
``account.json`` (state), ``trades.jsonl`` (immutable closed-trade ledger) and
``marks.jsonl`` (timestamped equity snapshots) -- and emits one JSON document.

Rules this module exists to enforce:

1. Nothing here computes P&L.  The engine already did that; this reads it.
2. Fees, funding and liquidation fees are reported as *attribution* of
   ``realized_net_pnl``, never subtracted from it again.  ``close_position``
   folds them in at close time, so the naive
   ``realized + unrealized + funding - fees`` aggregation double-counts.
   ``assert_ledger_invariants`` fails loudly if that ever creeps back.
3. Metrics come from ``metrics.py``, i.e. from the ledger and the equity
   series, with explicit ``*_status`` when a figure is not yet supportable.

stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import metrics as M

SCHEMA_VERSION = 1

# Equity is a float sum over many fills; compare with a cash-rounding tolerance
# rather than exact equality.
INVARIANT_TOLERANCE = 1e-6


class LedgerInvariantError(AssertionError):
    """Raised when the DTO does not reconcile against the engine's own state."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@dataclass(slots=True)
class SessionMeta:
    """Descriptive facts about a session that the engine does not itself track."""

    session_id: str
    strategy_id: str = "unknown"
    strategy_type: str = "futures_paper_engine"
    worker_id: str = ""
    timeframe: str = "15m"
    symbols: tuple[str, ...] = ()
    leverage: int = 5
    margin_mode: str = "isolated"
    market_source: str = "synthetic"
    contract_type: str = "USDT_PERPETUAL"
    price_kind: str = "mark_price"
    notes: str = ""


def position_dto(row: dict[str, Any]) -> dict[str, Any]:
    """One open position, with side taken from the position itself.

    ``side`` is authoritative here.  The dashboard previously inferred direction
    from a separate book-quantity map, which rendered shorts as longs; consumers
    must read this field and never re-derive it.
    """
    margin = float(row.get("isolated_margin") or 0.0)
    gross = float(row.get("unrealized_gross_pnl") or 0.0)
    net = float(row.get("unrealized_net_pnl") or 0.0)
    return {
        "trade_id": row.get("trade_id"),
        "symbol": row.get("symbol"),
        "side": str(row.get("side", "")).lower(),
        "direction": 1 if str(row.get("side", "")).lower() == "long" else -1,
        "margin_mode": row.get("margin_mode", "isolated"),
        "leverage": row.get("leverage"),
        "isolated_margin": margin,
        "notional": float(row.get("notional") or 0.0),
        "quantity": float(row.get("quantity") or 0.0),
        "entry_price": float(row.get("entry_price") or 0.0),
        "entry_time": row.get("entry_time"),
        "mark_price": float(row.get("mark_price") or 0.0),
        "take_profit_price": row.get("take_profit_price"),
        "stop_loss_price": row.get("stop_loss_price"),
        "liquidation_price": row.get("liquidation_price"),
        "entry_fee": float(row.get("entry_fee") or 0.0),
        "estimated_exit_fee": float(row.get("estimated_exit_fee") or 0.0),
        "accrued_funding": float(row.get("accrued_funding") or 0.0),
        "unrealized_gross_pnl": gross,
        "unrealized_net_pnl": net,
        # Gross ROI is kept for parity with exchange displays; net ROI is the
        # one that answers "what has this position actually earned me".
        "margin_roi_gross_pct": float(row.get("margin_roi_pct") or 0.0),
        "margin_roi_net_pct": (net / margin * 100.0) if margin > 0 else None,
        "signal_reason": row.get("signal_reason"),
        "market_regime": row.get("market_regime"),
    }


def closed_trade_dto(row: dict[str, Any]) -> dict[str, Any]:
    """One closed trade, passed through from the ledger without recomputation."""
    return {
        "trade_id": row.get("trade_id"),
        "symbol": row.get("symbol"),
        "side": str(row.get("side", "")).lower(),
        "leverage": row.get("leverage"),
        "margin_used": float(row.get("margin_used") or 0.0),
        "notional": float(row.get("notional") or 0.0),
        "quantity": float(row.get("quantity") or 0.0),
        "entry_time": row.get("entry_time"),
        "exit_time": row.get("exit_time"),
        "entry_price": float(row.get("entry_price") or 0.0),
        "exit_price": float(row.get("exit_price") or 0.0),
        "gross_pnl": float(row.get("gross_pnl") or 0.0),
        "entry_fee": float(row.get("entry_fee") or 0.0),
        "exit_fee": float(row.get("exit_fee") or 0.0),
        "funding_paid": float(row.get("funding_paid") or 0.0),
        "liquidation_fee": float(row.get("liquidation_fee") or 0.0),
        # Already net of every cost above -- do not subtract them again.
        "net_pnl": float(row.get("net_pnl") or 0.0),
        "roi_pct": float(row.get("roi_pct") or 0.0),
        "hold_seconds": float(row.get("hold_seconds") or 0.0),
        "entry_reason": row.get("entry_reason"),
        "exit_reason": row.get("exit_reason"),
        "market_regime": row.get("market_regime"),
    }


def assert_ledger_invariants(dto: dict[str, Any], tolerance: float = INVARIANT_TOLERANCE) -> None:
    """Fail loudly if the published numbers do not reconcile.

    Checked here rather than in a test so a corrupted session can never be
    served to the dashboard as if it were sound.
    """
    starting = dto["starting_equity"]
    equity = dto["current_equity"]
    net = dto["net_pnl"]
    realized = dto["realized_net_pnl"]
    unrealized = dto["unrealized_gross_pnl"]
    open_costs = dto["open_position_costs"]

    if abs((starting + net) - equity) > tolerance:
        raise LedgerInvariantError(
            f"equity identity violated: starting {starting} + net {net} != equity {equity}"
        )
    if abs((realized + unrealized - open_costs) - net) > tolerance:
        raise LedgerInvariantError(
            f"net_pnl must be realized_net_pnl + unrealized_gross_pnl - open_position_costs; "
            f"{realized} + {unrealized} - {open_costs} != {net}"
        )
    if abs((dto["wallet_balance"] + unrealized) - equity) > tolerance:
        raise LedgerInvariantError(
            f"wallet {dto['wallet_balance']} + unrealized {unrealized} != equity {equity}"
        )

    stats = dto["metrics"]["trade_stats"]
    if stats["closed_trades"] != len(dto["closed_trades"]):
        raise LedgerInvariantError(
            f"trade_stats.closed_trades {stats['closed_trades']} != "
            f"{len(dto['closed_trades'])} ledger rows"
        )
    if abs(stats["realized_net_pnl"] - realized) > 1e-4:
        raise LedgerInvariantError(
            f"sum of closed-trade net_pnl {stats['realized_net_pnl']} != "
            f"account realized_net_pnl {realized}"
        )


def build_session_dto(
    session_dir: str | Path,
    meta: SessionMeta,
    *,
    snapshot: Optional[dict[str, Any]] = None,
    resample_seconds: int = M.DEFAULT_RESAMPLE_SECONDS,
    verify: bool = True,
) -> dict[str, Any]:
    """Assemble the canonical session document for one engine session directory.

    ``snapshot`` may be supplied by a live engine instance (avoiding a second
    mark fetch); otherwise the most recent row of ``marks.jsonl`` is used.
    """
    path = Path(session_dir)
    account = _read_json(path / "account.json")
    trades = _read_jsonl(path / "trades.jsonl")
    marks = _read_jsonl(path / "marks.jsonl")

    if snapshot is None:
        snapshot = marks[-1] if marks else {}

    starting = float(account.get("initial_balance") or snapshot.get("initial_balance") or 0.0)
    wallet = float(snapshot.get("wallet_balance", account.get("wallet_balance", starting)))
    unrealized_gross = float(snapshot.get("unrealized_pnl") or 0.0)
    realized_net = float(account.get("realized_net_pnl") or 0.0)
    equity = wallet + unrealized_gross

    open_positions = [position_dto(p) for p in snapshot.get("open_positions", [])]
    closed = [closed_trade_dto(t) for t in trades]

    # marks.jsonl is the timestamped equity series -- one row per engine tick,
    # written by record_mark. Metrics resample it onto a fixed grid, so the
    # tick rate cannot influence them.
    equity_points = [
        {"timestamp": m["timestamp"], "equity": float(m["current_equity"])}
        for m in marks
        if m.get("timestamp") is not None and m.get("current_equity") is not None
    ]

    trade_stats = M.compute_trade_stats(trades)
    risk = M.compute_risk_metrics(equity_points, resample_seconds=resample_seconds)

    unrealized_net = sum(p["unrealized_net_pnl"] for p in open_positions)

    # Entry fees and settled funding on *still-open* positions have already left
    # the wallet but are not yet in realized_net_pnl -- they only land there when
    # the position closes.  Omitting them breaks the equity identity by exactly
    # the open positions' paid costs, so they are carried explicitly.  The
    # estimated exit fee is deliberately not included: it has not been incurred.
    open_costs = sum(p["entry_fee"] + p["accrued_funding"] for p in open_positions)

    dto: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "session_id": meta.session_id,
        "mode": "paper_engine",
        "data_source": "futures_paper_engine",
        "engine": "backend/agent/futures_paper_engine.py",
        "session": {
            "strategy_id": meta.strategy_id,
            "strategy_type": meta.strategy_type,
            "worker_id": meta.worker_id or meta.session_id,
            "timeframe": meta.timeframe,
            "symbols": list(meta.symbols),
            "leverage": meta.leverage,
            "margin_mode": meta.margin_mode,
            "contract_type": meta.contract_type,
            "market_source": meta.market_source,
            "price_kind": meta.price_kind,
            "notes": meta.notes,
        },
        "started_at": marks[0]["timestamp"] if marks else account.get("updated_at"),
        "updated_at": snapshot.get("timestamp") or account.get("updated_at"),

        # --- account -----------------------------------------------------
        "starting_equity": starting,
        "wallet_balance": wallet,
        "available_balance": float(snapshot.get("available_balance", wallet)),
        "reserved_margin": float(snapshot.get("reserved_margin") or 0.0),
        "open_notional": float(snapshot.get("open_notional") or 0.0),
        "current_equity": equity,

        # --- P&L components ----------------------------------------------
        # realized_net_pnl already contains fees, funding and liquidation fees.
        # The three attribution fields below explain it; they are not further
        # deductions.
        "realized_gross_pnl": float(account.get("realized_gross_pnl") or 0.0),
        "realized_net_pnl": realized_net,
        "unrealized_gross_pnl": unrealized_gross,
        "unrealized_net_pnl": unrealized_net,
        "fees_paid": float(account.get("total_fees") or 0.0),
        "funding_pnl": -float(account.get("total_funding") or 0.0),
        "liquidation_fees": float(account.get("total_liquidation_fees") or 0.0),
        "open_position_costs": open_costs,
        "net_pnl": realized_net + unrealized_gross - open_costs,
        "account_return": (equity / starting - 1.0) if starting > 0 else None,
        "margin_usage": (float(snapshot.get("reserved_margin") or 0.0) / wallet) if wallet > 0 else None,

        # --- collections --------------------------------------------------
        "open_positions": open_positions,
        "closed_trades": closed,
        "equity_curve": equity_points,

        # --- metrics ------------------------------------------------------
        "metrics": {
            "trade_stats": trade_stats.to_dict(),
            "risk": risk.to_dict(),
        },
    }

    if verify:
        assert_ledger_invariants(dto)
    return dto
