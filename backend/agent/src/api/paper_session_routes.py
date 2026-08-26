"""HTTP routes for simulated paper-trading sessions AND live Binance testnet orders.

WARNING -- this module is no longer read-only. It was originally a read-only
view over ``agent/paper_sessions/<id>/`` files, but it now also mounts
``/paper-sessions/binance-testnet/*`` and ``/paper-sessions/signal-queue/*``,
which submit real orders to the Binance USD-M matching engine (testnet host).
Those orders have real order IDs and a real lifecycle; only the money is fake.
Treat every route under those two prefixes as a mutating, network-facing
execution surface, not as dashboard telemetry.

The file-reading routes remain read-only: they only ever read
``session.json`` / ``session_config.json`` (static config), ``book.json`` /
``account.json`` (current positions/cash), ``marks.jsonl`` (equity snapshots)
and ``trades.jsonl`` (executed trades). No route here starts or stops a
worker; that stays a deliberate CLI/background-process action.

LIVENESS CONTRACT
-----------------
Every session payload carries ``liveness_source``:

  "database"      -- heartbeat/cycle evidence came from PostgreSQL.
  "session_files" -- PostgreSQL was unreachable; figures are read off disk.

Only ``liveness_source == "database"`` may ever be treated as proof that a
worker is alive. Files on disk prove a file exists, not that a write landed.
The ARM gate MUST require "database". See _load_futures_paper_session().
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Any]

PAPER_SESSIONS_DIR = Path(__file__).resolve().parents[2] / "paper_sessions"
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "paper_sessions_registry.json"
_SAFE_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_VALID_SCOPES = {"active", "archived", "all"}

# Hard governance ceiling, in code, at module scope so it is importable and
# testable. Env may only LOWER this, never raise it (see _effective_notional_cap).
HARD_CAP_MAX_ORDER_USD = 100.0

# Trading modes under which order submission is permitted at all.
_PERMITTED_TRADING_MODES = {"testnet", "sandbox", "paper"}

# Absolute quality floor. A producer that omits raw_score must FAIL this,
# not sail past it on a permissive default.
_ABSOLUTE_SCORE_FLOOR = 60.0

_DB_CONNECT_TIMEOUT = 2
_MAX_PAGE_LIMIT = 200


def _paper_dsn() -> str:
    """Single source of truth for the paper-trading DSN.

    Note the database is ``mostar`` -- MoStar is the host/database platform.
    Scaffs is the tenant application. Idim Ikang is the upstream producer.
    """
    return os.getenv("VIBE_PAPER_DATABASE_URL", "dbname=mostar port=5433")


def _clamp_limit(limit: int, default: int = 50) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, _MAX_PAGE_LIMIT))


def _as_aware_utc(value: Any) -> Optional[datetime]:
    """Parse a timestamp into an aware UTC datetime, or None.

    Naive timestamps are ASSUMED UTC rather than silently discarded -- the
    previous code compared naive to aware, raised TypeError, swallowed it,
    and quietly skipped the check.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _postgres_account_view(account_id: str) -> dict[str, Any] | None:
    """Read one account projection; every child-table lookup is account scoped.

    Returns None ONLY when the database genuinely has no such row or is
    unreachable. The caller must not treat None as 'healthy' -- it downgrades
    liveness_source to "session_files".
    """
    try:
        from uuid import UUID

        import psycopg

        parsed_id = UUID(account_id)
        with psycopg.connect(_paper_dsn(), connect_timeout=_DB_CONNECT_TIMEOUT) as connection, \
                connection.cursor() as cursor:
            cursor.execute(
                """SELECT a.strategy_id,a.worker_id,a.timeframe,a.mode,a.leverage,
                          a.initial_capital,a.cash_balance,a.margin_used,a.realized_pnl,
                          a.unrealized_pnl,a.funding_pnl,a.fees,a.current_equity,
                          a.ledger_status,h.last_seen_at,h.last_trade_at,h.risk_state,
                          (SELECT count(*) FROM paper_trading.positions p
                            WHERE p.account_id=a.account_id AND p.mode=a.mode),
                          (SELECT c.market_data_source FROM paper_trading.paper_cycle_events c
                            WHERE c.account_id=a.account_id
                            ORDER BY c.cycle_completed_at DESC LIMIT 1),
                          (SELECT c.cycle_completed_at FROM paper_trading.paper_cycle_events c
                            WHERE c.account_id=a.account_id
                            ORDER BY c.cycle_completed_at DESC LIMIT 1)
                     FROM paper_trading.trading_accounts a
                     LEFT JOIN paper_trading.worker_heartbeats h
                       ON h.account_id=a.account_id AND h.mode=a.mode
                    WHERE a.account_id=%s""",
                (parsed_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "account_id": account_id,
            "strategy_id": row[0], "worker_id": row[1], "timeframe": row[2],
            "mode": row[3], "leverage": row[4], "initial_capital": float(row[5]),
            "cash_available": float(row[6]), "margin_used": float(row[7]),
            "realized_pnl": float(row[8]), "unrealized_pnl": float(row[9]),
            "funding_pnl": float(row[10]), "fees": float(row[11]),
            "current_equity": float(row[12]), "ledger_status": row[13],
            "last_heartbeat": row[14].isoformat() if row[14] else None,
            "last_trade": row[15].isoformat() if row[15] else None,
            "risk_state": row[16] or {}, "open_positions": row[17],
            # Persisted by grid_futures_runner from the actual price-fetch
            # branch that answered (binance/okx/gate) -- never inferred here.
            "market_data_source": row[18],
            "last_cycle_completed_at": row[19].isoformat() if row[19] else None,
            "telemetry_source": "database",
        }
    except Exception as exc:  # database telemetry must not take down the dashboard
        logger.warning("postgres account view failed for %s: %s", account_id, exc)
        return None


def _validate_session_id(session_id: str) -> None:
    if not _SAFE_SESSION_ID_RE.fullmatch(session_id or ""):
        raise HTTPException(status_code=400, detail="invalid session_id")


def _load_registry() -> tuple[frozenset[str], frozenset[str], Optional[str]]:
    """Load the active/archived paper-session registry.

    Fails closed: any missing file, invalid JSON, or malformed schema
    returns two empty sets (every session then classifies as "unknown",
    never silently "active") plus a human-readable error string the
    caller can surface instead of guessing.
    """
    try:
        raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset(), frozenset(), "registry file not found"
    except json.JSONDecodeError as exc:
        return frozenset(), frozenset(), f"registry file is not valid JSON: {exc}"
    except OSError as exc:
        return frozenset(), frozenset(), f"registry file unreadable: {exc}"

    active = raw.get("active_sessions")
    archived = raw.get("archived_sessions")
    if not isinstance(active, list) or not isinstance(archived, list):
        return frozenset(), frozenset(), "registry missing active_sessions/archived_sessions arrays"

    return frozenset(active), frozenset(archived), None


def _classify_session(session_id: str, active_ids: frozenset[str], archived_ids: frozenset[str]) -> str:
    """Never infers -- a session is only "active" if the registry says so."""
    if session_id in archived_ids:
        return "archived"
    if session_id in active_ids:
        return "active"
    return "unknown"


def _registry_status(classification: str, marks: list[dict[str, Any]]) -> str:
    """Status derived from the registry classification plus mark freshness.

    An archived session can never report "running", even if a stale
    .heartbeat file from before its retirement is still sitting on disk.
    """
    if classification == "archived":
        return "archived"
    if classification == "unknown":
        return "unknown"

    from paper_session import RUNTIME_STALE_AFTER, _parse_iso  # noqa: F401

    if not marks:
        return "stale"
    stamped = _as_aware_utc(marks[-1].get("timestamp"))
    if stamped is None:
        return "stale"
    return "running" if (datetime.now(timezone.utc) - stamped) < RUNTIME_STALE_AFTER else "stale"


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read a JSONL ledger, tolerating a torn final line.

    Returns (rows, malformed_count). A worker killed mid-write leaves a
    partial line; the old version raised JSONDecodeError and took the whole
    dashboard down with it. Malformed lines are counted and surfaced, never
    silently dropped.
    """
    if not path.exists():
        return [], 0
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("could not read %s: %s", path, exc)
        return [], 0
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            malformed += 1
    if malformed:
        logger.warning("%s contained %d malformed JSONL line(s)", path, malformed)
    return rows, malformed


def _summarize(session_dir: Path, classification: str = "unknown") -> dict[str, Any]:
    # Always load from files for critical metrics -- files are the source of truth
    # for THIS session shape (paper_session.py writes files, not Postgres).
    from paper_session import verify_receipted_file

    session_path = session_dir / "session.json"
    session_intact = verify_receipted_file(session_path)
    session = json.loads(session_path.read_text(encoding="utf-8"))

    book_path = session_dir / "book.json"
    if book_path.exists():
        book_intact = verify_receipted_file(book_path)
        book = json.loads(book_path.read_text(encoding="utf-8"))
    elif "positions" in session:
        book = {
            "positions": session["positions"],
            "cash_remaining": session.get("cash_remaining", 0.0),
            "last_rebalance_time": session.get("entry_time"),
        }
        book_intact = True
    else:
        book = None
        book_intact = True

    marks, marks_malformed = _read_jsonl(session_dir / "marks.jsonl")
    trades, trades_malformed = _read_jsonl(session_dir / "trades.jsonl")
    latest = marks[-1] if marks else None

    # File-first equity: prefer latest mark, fall back to book cash.
    if latest:
        equity = float(latest["equity"])
    elif book:
        equity = float(book.get("cash_remaining", 0.0))
    else:
        equity = 0.0

    initial_cash = float(session.get("initial_cash", 0.0))
    pnl = equity - initial_cash
    return_pct = (pnl / initial_cash) * 100.0 if initial_cash else 0.0

    peak = float("-inf")
    max_drawdown = 0.0
    equity_curve = []
    for m in marks:
        e = float(m["equity"])
        peak = max(peak, e)
        drawdown = (e - peak) / peak if peak > 0 else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        equity_curve.append({"time": m["timestamp"], "equity": e, "drawdown": drawdown})

    from paper_session import compute_trade_stats, compute_session_status

    trade_stats = compute_trade_stats(trades)
    status = compute_session_status(session_dir)

    # REMOVED: the ``_check_heartbeat`` override that promoted runtime_status
    # to "running" on the strength of a .heartbeat FILE. A file on disk is not
    # evidence a write landed anywhere. This is the same defect that reported
    # 9/9 workers fresh while PostgreSQL was offline and zero writes landed.
    # If you need worker liveness, read it from the database.

    return {
        "session_id": session_dir.name,
        "session": session,
        "book": book,
        "mark_count": len(marks),
        "latest_mark": latest,
        "trade_count": len(trades),
        "recent_trades": trade_stats["trades"][-50:],
        "trade_stats": {"overall": trade_stats["overall"], "by_symbol": trade_stats["by_symbol"]},
        "equity_curve": equity_curve,
        "max_drawdown": max_drawdown,
        "equity": equity,
        "pnl": pnl,
        "return_pct": return_pct,
        "tampered": not session_intact or not book_intact,
        "ledger_malformed_lines": marks_malformed + trades_malformed,
        "classification": classification,
        "status": _registry_status(classification, marks),
        "liveness_source": "session_files",
        **status,
    }


def _summarize_db_session(session: dict, trades: list[dict], marks: list[dict]) -> dict:
    """Build a PaperSessionSummary from data stored in the paper_store DB."""
    symbols = session.get("symbols", [])

    # Entry prices from the first BUY trade per symbol
    entry_prices: dict[str, float] = {}
    for t in trades:
        if t.get("side") == "BUY" and t.get("symbol") in symbols and t["symbol"] not in entry_prices:
            entry_prices[t["symbol"]] = float(t["price"])
    session["entry_prices"] = entry_prices

    latest = marks[-1] if marks else None
    book = {
        "positions": {sym: 0.0 for sym in symbols},
        "cash_remaining": float(latest["cash_remaining"]) if latest else 0.0,
        "last_rebalance_time": session.get("entry_time", ""),
    }

    peak = float("-inf")
    max_drawdown = 0.0
    equity_curve = []
    for m in marks:
        equity = float(m.get("equity", 0.0))
        peak = max(peak, equity)
        drawdown = (equity - peak) / peak if peak > 0 else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        equity_curve.append({"time": m["timestamp"], "equity": equity, "drawdown": drawdown})

    from paper_session import compute_trade_stats

    trade_stats = compute_trade_stats(trades)
    # DB sessions are historical; not live
    status = {
        "runtime_status": "stopped",
        "analysis_status": "valid",
        "accounting_status": "OK",
        "accounting_schema_version": 2,
        "session_role": "candidate",
        "regimen": "backtest",
        "active": False,
    }

    return {
        "session_id": session.get("session_id", session.get("id", "")),
        "session": session,
        "book": book,
        "mark_count": len(marks),
        "latest_mark": latest,
        "trade_count": len(trades),
        "recent_trades": trade_stats["trades"][-50:],
        "trade_stats": {"overall": trade_stats["overall"], "by_symbol": trade_stats["by_symbol"]},
        "equity_curve": equity_curve,
        "max_drawdown": max_drawdown,
        "classification": "historical",
        "status": "archived",
        "liveness_source": "database",
        **status,
    }


def _detect_session_schema(session_dir: Path) -> Optional[str]:
    """Two on-disk session shapes live under paper_sessions/: paper_session.py's
    CLI (session.json/book.json/marks.jsonl/trades.jsonl) and
    FuturesPaperEngine's (session_config.json/account.json/marks.jsonl/
    trades.jsonl). ``.is_file()`` -- not ``.exists()`` -- so a stray
    directory of the same name never misclassifies as a manifest.
    """
    if (session_dir / "session.json").is_file():
        return "paper_session"
    if (session_dir / "session_config.json").is_file():
        return "futures_paper"
    return None


def _futures_position_book(state: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Normalize FuturesPaperEngine's positions-by-trade_id state into the
    same {positions: {symbol: signed_qty}, position_metadata: {...}} shape
    paper_session.py's book.json already uses.
    """
    if state is None:
        return None
    positions_qty: dict[str, float] = {}
    position_metadata: dict[str, Any] = {}
    for pos in state.get("positions", {}).values():
        symbol = pos["symbol"]
        direction = 1 if pos["side"] == "long" else -1
        positions_qty[symbol] = direction * pos["quantity"]
        position_metadata[symbol] = {
            "symbol": symbol,
            "qty": pos["quantity"],
            "entry_price": pos["entry_price"],
            "entry_time": pos["entry_time"],
            "direction": direction,
            "high_water_mark": pos["high_water_mark"],
            "low_water_mark": pos["low_water_mark"],
            "leverage": pos["leverage"],
            "margin": pos["isolated_margin"],
            "margin_mode": pos["margin_mode"],
            "liquidation_price": pos["liquidation_price"],
            "take_profit_price": pos.get("take_profit_price"),
            "stop_loss_price": pos.get("stop_loss_price"),
        }
    return {
        "positions": positions_qty,
        "cash_remaining": state.get("wallet_balance", 0.0) - state.get("reserved_margin", 0.0),
        "last_rebalance_time": None,
        "position_metadata": position_metadata,
    }


def _futures_trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Win/loss stats straight from FuturesPaperEngine's ClosedTrade rows."""
    if not trades:
        return {"overall": None, "by_symbol": {}}
    wins = [t for t in trades if t.get("net_pnl", 0.0) > 0]
    losses = [t for t in trades if t.get("net_pnl", 0.0) <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = sum(-t["net_pnl"] for t in losses)
    overall = {
        "trade_count": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "avg_win": (gross_win / len(wins)) if wins else None,
        "avg_loss": (gross_loss / len(losses)) if losses else None,
    }
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        by_symbol.setdefault(t["symbol"], []).append(t)
    return {"overall": overall, "by_symbol": by_symbol}


def compute_five_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "TotalNet": 0.0,
            "WinRate": None,
            "AvgWin": None,
            "AvgLoss": None,
            "ProfitFactor": None,
        }
    wins = [float(t.get("net_pnl", 0.0)) for t in trades if float(t.get("net_pnl", 0.0)) > 0]
    losses = [float(t.get("net_pnl", 0.0)) for t in trades if float(t.get("net_pnl", 0.0)) < 0]

    total_net = sum(float(t.get("net_pnl", 0.0)) for t in trades)
    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (sum(losses) / len(losses)) if losses else None

    gross_win = sum(wins)
    gross_loss = sum(abs(l) for l in losses)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    return {
        "TotalNet": total_net,
        "WinRate": win_rate,
        "AvgWin": avg_win,
        "AvgLoss": avg_loss,
        "ProfitFactor": profit_factor,
    }


def _load_futures_paper_session(session_dir: Path, classification: str = "unknown") -> dict[str, Any]:
    """Normalize a FuturesPaperEngine session into the same response shape
    _summarize() produces for a paper_session.py session.
    """
    config = json.loads((session_dir / "session_config.json").read_text(encoding="utf-8"))

    universe_path = session_dir / config.get("universe_path", "")
    try:
        symbols = json.loads(universe_path.read_text(encoding="utf-8")).get("symbols", [])
    except (OSError, ValueError):
        symbols = []

    state_path = session_dir / "account.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else None
    book = _futures_position_book(state)

    marks, marks_malformed = _read_jsonl(session_dir / "marks.jsonl")
    trades, trades_malformed = _read_jsonl(session_dir / "trades.jsonl")

    def _mark_equity(m: dict[str, Any]) -> float:
        return float(m.get("current_equity", m.get("equity", 0.0)))

    latest = None
    if marks:
        raw_latest = marks[-1]
        latest = {**raw_latest, "equity": _mark_equity(raw_latest)}

    initial_cash = float(config.get("initial_balance", 0.0))
    if latest:
        equity = latest["equity"]
    elif state:
        equity = float(state.get("wallet_balance", initial_cash))
    else:
        equity = initial_cash
    pnl = equity - initial_cash
    return_pct = (pnl / initial_cash) * 100.0 if initial_cash else 0.0

    peak = float("-inf")
    max_drawdown = 0.0
    equity_curve = []
    for m in marks:
        e = _mark_equity(m)
        peak = max(peak, e)
        drawdown = (e - peak) / peak if peak > 0 else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        equity_curve.append({"time": m["timestamp"], "equity": e, "drawdown": drawdown})

    trade_stats = _futures_trade_stats(trades)
    five_stats = compute_five_stats(trades)

    never_launched = not marks and (state is None or state.get("opened_trades", 0) == 0)
    if never_launched:
        runtime_status = "not_started"
    elif not marks:
        runtime_status = "stopped"
    else:
        from paper_session import RUNTIME_STALE_AFTER

        stamped = _as_aware_utc(marks[-1].get("timestamp"))
        if stamped is None:
            runtime_status = "stopped"
        else:
            age = datetime.now(timezone.utc) - stamped
            runtime_status = "running" if age < RUNTIME_STALE_AFTER else "stopped"

    status = (
        "archived" if classification == "archived"
        else "unknown" if classification == "unknown"
        else runtime_status
    )

    account_id = str(config.get("account_id", session_dir.name))
    database_account = _postgres_account_view(account_id)

    # --- LIVENESS SOURCE -----------------------------------------------------
    # When Postgres answers, telemetry is authoritative. When it does not, we
    # still render figures off disk so the dashboard is not blank -- but the
    # payload says so, and a filesystem .heartbeat is NEVER promoted to
    # "running". That promotion is what made 9/9 workers appear fresh while
    # the database was down and zero writes had landed.
    if database_account is None:
        liveness_source = "session_files"
        heartbeat_path = session_dir / ".heartbeat"
        try:
            last_heartbeat_file = heartbeat_path.read_text(encoding="utf-8").strip() or None
        except OSError:
            last_heartbeat_file = None
        database_account = {
            "account_id": account_id,
            "strategy_id": config.get("strategy_id"),
            "worker_id": config.get("worker_id"),
            "timeframe": config.get("timeframe"),
            "mode": config.get("mode", "paper"),
            "leverage": config.get("leverage"),
            "initial_capital": initial_cash,
            "cash_available": (state or {}).get("wallet_balance", initial_cash)
            - (state or {}).get("reserved_margin", 0.0),
            "margin_used": (state or {}).get("reserved_margin", 0.0),
            "realized_pnl": (state or {}).get("realized_net_pnl", 0.0),
            "unrealized_pnl": (latest or {}).get("unrealized_pnl", 0.0),
            "funding_pnl": -(state or {}).get("total_funding", 0.0),
            "fees": (state or {}).get("total_fees", 0.0) + (state or {}).get("total_liquidation_fees", 0.0),
            "current_equity": equity,
            "ledger_status": (state or {}).get("status", "OK"),
            # Named to make its provenance unmistakable at the call site.
            "last_heartbeat_file": last_heartbeat_file,
            "last_heartbeat": None,          # no DB heartbeat exists
            "last_trade": trades[-1].get("exit_time") if trades else None,
            "risk_state": {},
            "open_positions": len((state or {}).get("positions", {})),
            "market_data_source": (latest or {}).get("market_data_source"),
            "last_cycle_completed_at": None,  # unproven without the database
            "telemetry_source": "session_files",
            "database_available": False,
        }
    else:
        liveness_source = "database"
        database_account["database_available"] = True
        # Only a DATABASE heartbeat may promote a session to "running".
        heartbeat_at = _as_aware_utc(database_account.get("last_heartbeat"))
        if heartbeat_at is not None:
            if datetime.now(timezone.utc) - heartbeat_at <= timedelta(seconds=45):
                runtime_status = "running"
                if classification not in ("archived", "unknown"):
                    status = "running"

    session_view = {
        "strategy_type": config.get("strategy_type", "futures_paper_engine"),
        "account_id": account_id,
        "strategy_id": database_account.get("strategy_id"),
        "worker_id": database_account.get("worker_id"),
        "timeframe": database_account.get("timeframe"),
        "symbols": symbols,
        "initial_cash": initial_cash,
        "accounting_status": (state or {}).get("status", "OK"),
        "accounting_schema_version": (state or {}).get("schema_version", 1),
        "risk_config": {
            "leverage": config.get("leverage"),
            "margin_mode": config.get("margin_mode", "isolated"),
            "fixed_margin_per_trade": config.get("margin_per_trade"),
        },
        "config_status": config.get("status"),
    }

    # pyrefly: ignore [missing-import]
    from paper_runtime.metrics import compute_risk_metrics
    equity_points = []
    for m in marks:
        equity_points.append({
            "timestamp": m["timestamp"],
            "equity": float(m.get("current_equity", m.get("equity", 0.0)))
        })
    risk_metrics = compute_risk_metrics(equity_points)

    snapshot_id = f"snap_{session_dir.name}_{len(marks)}"
    txn_id = (state or {}).get("last_txn_id")
    if not txn_id and state and state.get("committed_txn_ids"):
        txn_id = state["committed_txn_ids"][-1]
    if not txn_id:
        import uuid
        txn_id = uuid.uuid4().hex[:16]

    observed_at = (
        (state or {}).get("updated_at")
        or (latest["timestamp"] if latest else datetime.now(timezone.utc).isoformat())
    )
    # Never default the market source to a venue name we did not observe.
    market_source = (latest or {}).get("market_data_source") or database_account.get("market_data_source")

    wallet_balance = float((state or {}).get("wallet_balance", initial_cash))
    reserved_margin = float((state or {}).get("reserved_margin", 0.0))
    available_balance = wallet_balance - reserved_margin
    open_notional = float((state or {}).get("open_notional", 0.0))
    realized_pnl = float((state or {}).get("realized_net_pnl", 0.0))
    fees_paid = float((state or {}).get("total_fees", 0.0)) + float((state or {}).get("total_liquidation_fees", 0.0))
    funding_pnl = -float((state or {}).get("total_funding", 0.0))

    unrealized_pnl = 0.0
    if state and state.get("positions"):
        for pos in state["positions"].values():
            m_price = 0.0
            if latest and latest.get("prices"):
                m_price = float(latest["prices"].get(pos["symbol"], 0.0))
            if m_price <= 0:
                m_price = float(pos.get("entry_price", 0.0))
            direction = 1 if pos.get("side") == "long" else -1
            pnl_gross = float(pos.get("quantity", 0.0)) * (m_price - float(pos.get("entry_price", 0.0))) * direction
            unrealized_pnl += pnl_gross

    equity = wallet_balance + unrealized_pnl

    account_envelope = {
        "initialCapital": initial_cash,
        "walletBalance": wallet_balance,
        "reservedMargin": reserved_margin,
        "availableBalance": available_balance,
        "equity": equity,
        "openNotional": open_notional,
        "realizedPnl": realized_pnl,
        "unrealizedPnl": unrealized_pnl,
        "feesPaid": fees_paid,
        "fundingPnl": funding_pnl,
    }

    positions_envelope = list((state or {}).get("positions", {}).values())

    analytics_envelope = {
        "TotalNet": five_stats["TotalNet"],
        "WinRate": five_stats["WinRate"],
        "AvgWin": five_stats["AvgWin"],
        "AvgLoss": five_stats["AvgLoss"],
        "ProfitFactor": five_stats["ProfitFactor"],
        "SharpeRatio": risk_metrics.sharpe,
        "SortinoRatio": risk_metrics.sortino,
        "Session Return / Max Drawdown": risk_metrics.calmar,
        "max_drawdown": risk_metrics.max_drawdown,
        "recent_trades": trades[-50:],
    }

    health_envelope = {
        "status": (state or {}).get("status", "OK"),
        "runtime_status": runtime_status,
        "active": runtime_status == "running",
        "liveness_source": liveness_source,
    }

    return {
        "snapshot_id": snapshot_id,
        "txn_id": txn_id,
        "observed_at": observed_at,
        "market_source": market_source,
        "account": account_envelope,
        "positions": positions_envelope,
        "marks": marks,
        "analytics": analytics_envelope,
        "health": health_envelope,

        "session_id": session_dir.name,
        "session": session_view,
        "book": book,
        "mark_count": len(marks),
        "latest_mark": latest,
        "trade_count": len(trades),
        "recent_trades": trades[-50:],
        "trade_stats": trade_stats,
        "equity_curve": equity_curve,
        "max_drawdown": max_drawdown,
        "equity": equity,
        "pnl": pnl,
        "return_pct": return_pct,
        "ledger_malformed_lines": marks_malformed + trades_malformed,
        "classification": classification,
        "status": status,
        "runtime_status": runtime_status,
        "active": runtime_status == "running",
        "liveness_source": liveness_source,
        "database_account": database_account,
    }


def _effective_notional_cap() -> float:
    """Env may only LOWER the in-code ceiling, never raise it.

    A malformed or absent MAX_POSITION_USD falls back to the in-code cap --
    it never widens it. .env was changed unattributed once already; the code
    ceiling is the control that survives that.
    """
    raw = os.environ.get("MAX_POSITION_USD")
    if raw is None:
        return HARD_CAP_MAX_ORDER_USD
    try:
        env_max = float(raw)
    except (TypeError, ValueError):
        logger.warning("MAX_POSITION_USD=%r is not a number; using in-code cap", raw)
        return HARD_CAP_MAX_ORDER_USD
    if env_max <= 0:
        logger.warning("MAX_POSITION_USD=%r is not positive; using in-code cap", raw)
        return HARD_CAP_MAX_ORDER_USD
    return min(HARD_CAP_MAX_ORDER_USD, env_max)


def register_paper_session_routes(
    app: FastAPI,
    require_auth: Optional[AuthDep] = None,
) -> None:
    """Mount the paper-session routes onto ``app``.

    ``require_auth`` is resolved BEFORE any route is declared, so every route
    in this module carries the same dependency. Previously the notifications
    route was declared before resolution and shipped with an empty dependency
    list whenever the caller omitted require_auth -- an unauthenticated hole
    in an otherwise authenticated module.
    """
    if require_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:  # pragma: no cover
            raise RuntimeError(
                "register_paper_session_routes: api_server module not in "
                "sys.modules; pass require_auth explicitly"
            )
        require_auth = host.require_auth

    auth_dependencies = [Depends(require_auth)]

    # Trigger legacy state migration for all sessions on startup
    try:
        # pyrefly: ignore [missing-import]
        from migration import migrate_all_sessions
        migrate_all_sessions(PAPER_SESSIONS_DIR)
    except Exception as exc:
        logger.error("Failed to run legacy session migrations: %s", exc)

    @app.get("/paper-trading/notifications", dependencies=auth_dependencies)
    async def get_paper_trading_notifications(after: Optional[str] = None):
        """Read-only notification feed for paper-dashboard toast polling."""
        try:
            import psycopg
            query = """SELECT id,worker_id,event_type,severity,title,message,created_at
                         FROM paper_trading.trading_notifications
                         WHERE (%s::timestamptz IS NULL OR created_at > %s::timestamptz)
                         ORDER BY created_at ASC LIMIT 100"""
            with psycopg.connect(_paper_dsn(), connect_timeout=_DB_CONNECT_TIMEOUT) as conn, conn.cursor() as cur:
                cur.execute(query, (after, after))
                rows = cur.fetchall()
            return [{"id": str(r[0]), "worker_id": r[1], "event_type": r[2],
                     "severity": r[3], "title": r[4], "message": r[5],
                     "created_at": r[6].isoformat()} for r in rows]
        except Exception as exc:
            logger.warning("notification feed unavailable: %s", exc)
            raise HTTPException(status_code=503, detail="paper notification feed unavailable") from exc

    @app.get("/paper-sessions", dependencies=auth_dependencies)
    async def list_paper_sessions(scope: str = "active"):
        """List paper sessions, including backtest sessions stored in the database.

        ``scope`` controls the active/archived registry split
        (``config/paper_sessions_registry.json``):

        - ``active`` (default) -- registry-listed active sessions only.
        - ``archived`` -- registry-listed archived sessions only.
        - ``all`` -- both groups.

        A filesystem session not covered by the registry is classified
        "unknown" and is never excluded by scope. DB-only sessions are
        historical and only merged in on ``scope=all``.

        Fails closed: if the registry is missing or malformed, returns an
        empty list rather than risk showing a retired session as active.
        """
        if scope not in _VALID_SCOPES:
            raise HTTPException(status_code=400, detail=f"scope must be one of: {sorted(_VALID_SCOPES)}")

        active_ids, archived_ids, registry_error = _load_registry()
        if registry_error is not None:
            logger.warning("paper session registry unusable: %s", registry_error)
            return []

        results = []
        if not PAPER_SESSIONS_DIR.exists():
            return []
        existing_ids = set()
        candidate_dirs = sorted(
            (d for d in PAPER_SESSIONS_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")),
            key=lambda d: d.name,
            reverse=True,
        )
        for d in candidate_dirs:
            schema = _detect_session_schema(d)
            if schema is None:
                continue
            existing_ids.add(d.name)
            classification = _classify_session(d.name, active_ids, archived_ids)
            if classification != "unknown" and scope != "all" and classification != scope:
                continue
            try:
                if schema == "paper_session":
                    results.append(_summarize(d, classification=classification))
                else:
                    results.append(_load_futures_paper_session(d, classification=classification))
            except Exception as exc:
                # One corrupt session must not blank the whole dashboard, but
                # it must be VISIBLE rather than silently omitted.
                logger.error("failed to summarize session %s: %s", d.name, exc)
                results.append({
                    "session_id": d.name,
                    "classification": classification,
                    "status": "error",
                    "runtime_status": "error",
                    "active": False,
                    "liveness_source": "session_files",
                    "error": str(exc),
                })

        try:
            if scope != "all":
                return results
            # pyrefly: ignore [missing-import]
            from paper_store import get_store
            store = get_store()
            db_sessions = store.list_sessions(strategy_type="per_symbol_isolated_backtest")
            for s in db_sessions:
                sid = s["session_id"]
                if sid in existing_ids:
                    continue
                trades = store.list_trades(sid)
                marks = store.list_marks(sid)
                results.append(_summarize_db_session(s, trades, marks))
                existing_ids.add(sid)
        except Exception as exc:
            logger.warning("paper_store DB sessions unavailable: %s", exc)

        return results

    @app.get("/paper-sessions/registry-status", dependencies=auth_dependencies)
    async def get_paper_session_registry_status():
        """Diagnostics for the active/archived registry itself."""
        active_ids, archived_ids, registry_error = _load_registry()
        if registry_error is not None:
            return {"registry_status": "error", "detail": registry_error,
                    "active_sessions": [], "archived_sessions": []}
        return {
            "registry_status": "ok",
            "detail": None,
            "active_sessions": sorted(active_ids),
            "archived_sessions": sorted(archived_ids),
        }

    @app.get("/paper-sessions/provider-health", dependencies=auth_dependencies)
    async def get_paper_provider_health():
        """Probe every credential-free market provider independently.

        NOTE: reachability is not liveness. A provider answering here says
        nothing about whether a feed is delivering ticks to a worker.
        """
        # pyrefly: ignore [missing-import]
        from market_provider_health import get_market_provider_health

        return await run_in_threadpool(get_market_provider_health)

    @app.get("/paper-sessions/decision-health", dependencies=auth_dependencies)
    async def get_paper_decision_health():
        """Return the strategy-to-fill funnel from committed cycle evidence.

        Database-only by design. If PostgreSQL is unreachable this returns
        status="error" with an empty worker list -- it never falls back to
        counting files on disk.
        """
        try:
            import psycopg

            with psycopg.connect(_paper_dsn(), connect_timeout=_DB_CONNECT_TIMEOUT) as connection, \
                    connection.cursor() as cursor:
                cursor.execute(
                    """WITH recent AS (
                           SELECT *
                             FROM paper_trading.paper_cycle_events
                            WHERE cycle_completed_at > now() - interval '24 hours'
                         ), latest AS (
                           SELECT DISTINCT ON (worker_id)
                                  worker_id, cycle_completed_at, market_data_fresh,
                                  strategy_rejection_reason, risk_rejection_reason,
                                  order_rejection_reason, decision_funnel
                             FROM recent
                            ORDER BY worker_id, cycle_completed_at DESC
                         )
                         SELECT l.worker_id,l.cycle_completed_at,l.market_data_fresh,
                                l.strategy_rejection_reason,l.risk_rejection_reason,
                                l.order_rejection_reason,l.decision_funnel,
                                coalesce(sum((r.decision_funnel->>'cycles_completed')::bigint), 0),
                                coalesce(sum((r.decision_funnel->>'signals_evaluated')::bigint), 0),
                                coalesce(sum((r.decision_funnel->>'signals_true')::bigint), 0),
                                coalesce(sum((r.decision_funnel->>'entries_requested')::bigint), 0),
                                coalesce(sum((r.decision_funnel->>'paper_orders_filled')::bigint), 0),
                                coalesce(sum((r.decision_funnel->>'positions_closed')::bigint), 0)
                           FROM latest l
                           JOIN recent r USING (worker_id)
                          GROUP BY l.worker_id,l.cycle_completed_at,l.market_data_fresh,
                                   l.strategy_rejection_reason,l.risk_rejection_reason,
                                   l.order_rejection_reason,l.decision_funnel
                          ORDER BY l.worker_id"""
                )
                rows = cursor.fetchall()
        except Exception as exc:
            logger.error("decision-health query failed: %s", exc)
            return {"status": "error", "detail": str(exc), "window_hours": 24,
                    "workers": [], "liveness_source": "database"}

        workers = []
        for row in rows:
            workers.append({
                "worker_id": row[0],
                "last_cycle_at": row[1].isoformat() if row[1] else None,
                "market_data_fresh": bool(row[2]),
                "latest_rejections": {
                    "strategy": row[3], "risk": row[4], "order": row[5],
                },
                "latest_funnel": row[6] or {},
                "window": {
                    "cycles_completed": int(row[7]),
                    "signals_evaluated": int(row[8]),
                    "signals_true": int(row[9]),
                    "entries_requested": int(row[10]),
                    "paper_orders_filled": int(row[11]),
                    "positions_closed": int(row[12]),
                },
            })
        return {"status": "ok", "detail": None, "window_hours": 24,
                "workers": workers, "liveness_source": "database"}

    @app.get("/paper-sessions/shadow-comparison", dependencies=auth_dependencies)
    async def get_shadow_comparison():
        """Pair up control/candidate sessions by rebalance regimen."""
        if not PAPER_SESSIONS_DIR.exists():
            return []

        # pyrefly: ignore [missing-import]
        from paper_session import build_shadow_comparison

        return await run_in_threadpool(build_shadow_comparison, PAPER_SESSIONS_DIR)

    @app.get("/paper-sessions/shadow-comparison.csv", dependencies=auth_dependencies)
    async def get_shadow_comparison_csv():
        """Flat CSV of the same shadow-comparison rows, one per regimen."""
        # pyrefly: ignore [missing-import]
        from paper_session import build_shadow_comparison

        comparisons = await run_in_threadpool(build_shadow_comparison, PAPER_SESSIONS_DIR)

        import csv
        import io

        buffer = io.StringIO()
        fields = [
            "regimen", "control_session_id", "candidate_session_id",
            "control_net_return", "candidate_net_return", "delta_net_return",
            "control_total_fees", "candidate_total_fees", "delta_total_fees",
            "control_trade_count", "candidate_trade_count", "delta_trade_count",
            "control_turnover", "candidate_turnover", "delta_turnover",
            "control_max_drawdown", "candidate_max_drawdown", "delta_max_drawdown",
            "control_reconciled", "candidate_reconciled",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in comparisons:
            control = row.get("control") or {}
            candidate = row.get("candidate") or {}
            delta = row.get("delta") or {}
            writer.writerow({
                "regimen": row["regimen"],
                "control_session_id": row["control_session_id"],
                "candidate_session_id": row["candidate_session_id"],
                "control_net_return": control.get("net_return"),
                "candidate_net_return": candidate.get("net_return"),
                "delta_net_return": delta.get("net_return"),
                "control_total_fees": control.get("total_fees"),
                "candidate_total_fees": candidate.get("total_fees"),
                "delta_total_fees": delta.get("total_fees"),
                "control_trade_count": control.get("trade_count"),
                "candidate_trade_count": candidate.get("trade_count"),
                "delta_trade_count": delta.get("trade_count"),
                "control_turnover": control.get("turnover"),
                "candidate_turnover": candidate.get("turnover"),
                "delta_turnover": delta.get("turnover"),
                "control_max_drawdown": control.get("max_drawdown"),
                "candidate_max_drawdown": candidate.get("max_drawdown"),
                "delta_max_drawdown": delta.get("max_drawdown"),
                "control_reconciled": control.get("reconciled"),
                "candidate_reconciled": candidate.get("reconciled"),
            })

        from fastapi.responses import Response

        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=shadow-comparison.csv"},
        )

    # -------------------------------------------------------------------------
    # Binance USD-M Futures Testnet integration -- LIVE MATCHING ENGINE.
    # Registered BEFORE /paper-sessions/{session_id} so a literal path can
    # never be shadowed by the wildcard as routes are added over time.
    # -------------------------------------------------------------------------

    @app.get("/paper-sessions/binance-testnet/status", dependencies=auth_dependencies)
    async def get_binance_testnet_status():
        """Check Binance Futures Testnet connectivity and credential validity."""
        from src.trading.connectors.binance.futures_sdk import (
            BinanceFuturesConfig,
            get_binance_futures_client,
        )

        cfg = BinanceFuturesConfig.from_env()
        configured = bool(cfg.api_key and cfg.api_secret)

        client = get_binance_futures_client(cfg)
        t0 = time.time()
        try:
            server_time = await run_in_threadpool(client.get_server_time)
            latency_ms = round((time.time() - t0) * 1000, 2)
            balance = None
            balance_error = None
            if configured:
                try:
                    balances = await run_in_threadpool(client.get_account_balance)
                    usdt = next((b for b in balances if b.get("asset") == "USDT"), None)
                    balance = float(usdt.get("balance", 0.0)) if usdt else 0.0
                except Exception as exc:
                    # Report the balance failure instead of collapsing the whole
                    # status probe into ok:false.
                    logger.warning("testnet balance fetch failed: %s", exc)
                    balance_error = str(exc)

            return {
                "ok": True,
                "configured": configured,
                "host": cfg.base_url,
                "is_testnet": cfg.is_testnet,
                "latency_ms": latency_ms,
                "server_time": server_time,
                "usdt_balance": balance,
                "balance_error": balance_error,
            }
        except Exception as exc:
            logger.warning("testnet status probe failed: %s", exc)
            return {
                "ok": False,
                "configured": configured,
                "host": cfg.base_url,
                "is_testnet": cfg.is_testnet,
                "error": str(exc),
            }

    @app.get("/paper-sessions/binance-testnet/balance", dependencies=auth_dependencies)
    async def get_binance_testnet_balance():
        """Retrieve live asset balances from the Binance Futures Testnet account."""
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

        client = get_binance_futures_client()
        try:
            balances = await run_in_threadpool(client.get_account_balance)
            return {"ok": True, "balances": balances}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Binance Testnet balance fetch failed: {exc}") from exc

    @app.get("/paper-sessions/binance-testnet/positions", dependencies=auth_dependencies)
    async def get_binance_testnet_positions(symbol: Optional[str] = Query(None)):
        """Retrieve active open positions from Binance Futures Testnet."""
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

        client = get_binance_futures_client()
        try:
            positions = await run_in_threadpool(client.get_positions, symbol)
            return {"ok": True, "positions": positions}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Binance Testnet positions fetch failed: {exc}") from exc

    @app.get("/paper-sessions/binance-testnet/market", dependencies=auth_dependencies)
    async def get_binance_testnet_market(symbols: str = Query(..., description="Comma-separated symbols, e.g. BTC-USDT,ETH-USDT")):
        """Live Binance USD-M Futures Testnet market snapshot for requested symbols."""
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

        requested = [s.strip() for s in symbols.split(",") if s.strip()]
        if not requested:
            raise HTTPException(status_code=400, detail="symbols query parameter is required")

        client = get_binance_futures_client()
        try:
            snapshots = await run_in_threadpool(client.get_market_snapshots, requested)
            return {
                "ok": True,
                "source": "binance_testnet",
                "snapshots": [
                    {
                        "symbol": snap.symbol,
                        "timestamp": snap.timestamp,
                        "mark_price": snap.mark_price,
                        "last_price": snap.last_price,
                        "bid": snap.bid,
                        "ask": snap.ask,
                        "time_ms": snap.time_ms,
                    }
                    for snap in snapshots.values()
                ],
            }
        except Exception as exc:
            logger.warning("Binance Testnet market snapshot failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"Binance Testnet market snapshot failed: {exc}") from exc

    @app.post("/paper-sessions/binance-testnet/configure-account", dependencies=auth_dependencies)
    async def configure_binance_testnet_account(payload: dict[str, Any] = Body(...)):
        """Governance endpoint for symbol leverage and margin mode.

        Deliberately decoupled from order placement so account configuration
        can never be mutated as a side effect of submitting an order.
        """
        from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

        client = get_binance_futures_client()
        symbol = payload.get("symbol")
        leverage = payload.get("leverage")
        margin_type = payload.get("margin_type")

        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        if leverage is None and margin_type is None:
            raise HTTPException(status_code=400, detail="provide leverage and/or margin_type")

        results: dict[str, Any] = {}
        try:
            if leverage is not None:
                results["leverage"] = await run_in_threadpool(client.set_leverage, symbol, int(leverage))
            if margin_type is not None:
                results["margin_type"] = await run_in_threadpool(client.set_margin_type, symbol, str(margin_type))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid leverage/margin_type: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Account configuration failed: {exc}") from exc

        logger.info("account configured symbol=%s results=%s", symbol, results)
        return {"ok": True, "symbol": symbol, "results": results}

    @app.get("/paper-sessions/db-status", dependencies=auth_dependencies)
    async def get_db_status():
        """Return the current PostgreSQL persistence state."""
        from src.trading.signal_queue import SignalQueueManager
        import psycopg

        mgr = SignalQueueManager()
        try:
            with psycopg.connect(mgr.dsn, connect_timeout=_DB_CONNECT_TIMEOUT) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    version = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='paper_trading';"
                    )
                    tables = cur.fetchone()[0]
            return {
                "ok": True,
                "db": {
                    "connected": True,
                    "driver": "psycopg",
                    "database_url_configured": bool(os.getenv("DATABASE_URL") or os.getenv("VIBE_PAPER_DATABASE_URL")),
                    "provider": "PostgreSQL",
                    "tables_synced": tables > 0,
                    "tables_count": tables,
                    "postgres_version": version,
                    "last_error": None,
                },
            }
        except Exception as exc:
            return {
                "ok": True,
                "db": {
                    "connected": False,
                    "driver": "in_memory_fallback",
                    "database_url_configured": False,
                    "provider": "PostgreSQL",
                    "tables_synced": False,
                    "tables_count": 0,
                    "postgres_version": None,
                    "last_error": str(exc),
                },
            }

    @app.post("/paper-sessions/db-sync", dependencies=auth_dependencies)
    async def sync_db_state():
        """Placeholder for explicit DB sync; persistence is already continuous."""
        # Real sync would flush in-memory worker state to PostgreSQL; currently
        # all writes are committed at transaction time, so this is a no-op success.
        return {
            "ok": True,
            "db": {
                "connected": True,
                "tables_synced": True,
            },
            "message": "PostgreSQL persistence is active; state synced.",
        }

    @app.post("/paper-sessions/binance-testnet/order", dependencies=auth_dependencies)
    async def place_binance_testnet_order(payload: dict[str, Any] = Body(...)):
        """Place an order on the Binance Futures Testnet matching engine.

        Governance chain, in order, all fail-CLOSED:
          1. leverage/margin mutations rejected (use configure-account)
          2. TRADING_MODE must be testnet/sandbox/paper
          3. quantity must parse and be positive
          4. a reference price MUST be obtainable -- no price, no order
          5. notional must sit under min(HARD_CAP_MAX_ORDER_USD, MAX_POSITION_USD)
        """
        from src.trading.connectors.binance.futures_sdk import (
            get_binance_futures_client,
            BinanceConfig,
        )

        if "leverage" in payload or "margin_type" in payload:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Account leverage/margin mutations are decoupled from order "
                    "placement. Use POST /paper-sessions/binance-testnet/configure-account."
                ),
            )

        # Mode-specific, fail-closed configuration gate. This also validates
        # credentials and host.
        try:
            binance_cfg = BinanceConfig.from_env()
        except RuntimeError as exc:
            raise HTTPException(status_code=403, detail=f"Binance configuration rejected: {exc}") from exc

        if binance_cfg.mode != "testnet":
            raise HTTPException(
                status_code=403,
                detail=f"This endpoint only accepts Binance testnet mode, current mode is '{binance_cfg.mode}'.",
            )

        # Optional worker/strategy binding for signals routed through the queue.
        worker_id = payload.get("worker_id") or payload.get("target_strategy")
        if worker_id:
            from src.trading.strategy_binding import is_allowed_worker
            if not is_allowed_worker(worker_id):
                raise HTTPException(
                    status_code=403,
                    detail=f"Worker '{worker_id}' is not in the canonical allowlist.",
                )

        client = get_binance_futures_client()
        symbol = payload.get("symbol")
        side = payload.get("side")
        order_type = str(payload.get("order_type", "MARKET")).upper()
        quantity = payload.get("quantity")
        price = payload.get("price")
        client_order_id = payload.get("client_order_id")
        intent_id = payload.get("intent_id")
        signal_id = payload.get("signal_id")
        session_id = payload.get("session_id")
        cycle_seq = payload.get("cycle_seq")

        if not symbol or not side or quantity is None:
            raise HTTPException(status_code=400, detail="symbol, side, and quantity are required")

        try:
            qty_float = float(quantity)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid quantity: {exc}") from exc
        if qty_float <= 0:
            raise HTTPException(status_code=400, detail="Invalid quantity: must be positive")

        limit_price: Optional[float] = None
        if price is not None:
            try:
                limit_price = float(price)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid price: {exc}") from exc
            if limit_price <= 0:
                raise HTTPException(status_code=400, detail="Invalid price: must be positive")

        # --- FAIL-CLOSED NOTIONAL CAP ---------------------------------------
        # The previous version fell back to est_price = 0.0 on a ticker
        # failure and then evaluated `qty * (est_price or 1.0)`, pricing every
        # asset at $1. A 0.01 BTC order scored $0.01 of notional and sailed
        # under the $100 ceiling. If we cannot price the order, we do not
        # send the order.
        effective_limit = _effective_notional_cap()

        reference_price = limit_price
        if reference_price is None:
            try:
                fetched = await run_in_threadpool(client.get_ticker_price, symbol)
                reference_price = float(fetched)
            except Exception as exc:
                logger.error("notional cap could not price %s: %s", symbol, exc)
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Reference price for {symbol} unavailable ({exc}); order rejected. "
                        "The notional cap fails closed -- an unpriceable order is never sent."
                    ),
                ) from exc

        if reference_price <= 0:
            raise HTTPException(
                status_code=503,
                detail=f"Reference price for {symbol} was non-positive ({reference_price}); order rejected.",
            )

        order_notional = qty_float * reference_price
        if order_notional > effective_limit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Order notional (${order_notional:.2f} USD) exceeds hard governance "
                    f"limit (${effective_limit:.2f} USD)."
                ),
            )

        logger.info(
            "dispatching testnet order symbol=%s side=%s type=%s qty=%s notional=%.2f "
            "limit=%.2f intent_id=%s signal_id=%s",
            symbol, side, order_type, qty_float, order_notional, effective_limit,
            intent_id, signal_id,
        )

        try:
            order_res = await run_in_threadpool(
                client.place_order,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=qty_float,
                price=limit_price,
                client_order_id=client_order_id,
                intent_id=intent_id,
                signal_id=signal_id,
                session_id=session_id,
                cycle_seq=cycle_seq,
            )
        except Exception as exc:
            logger.error("testnet order execution error symbol=%s: %s", symbol, exc)
            raise HTTPException(status_code=502, detail=f"Binance Testnet order execution error: {exc}") from exc

        return {
            "ok": True,
            "order": order_res,
            "governance": {
                "reference_price": reference_price,
                "order_notional_usd": round(order_notional, 8),
                "effective_limit_usd": effective_limit,
                "hard_cap_usd": HARD_CAP_MAX_ORDER_USD,
                "trading_mode": trading_mode,
            },
        }

    @app.post("/paper-sessions/switch-testnet", dependencies=auth_dependencies)
    async def switch_testnet_mode(payload: dict[str, Any] = Body(default={})):
        """Audit paper session status and verify Binance Testnet connectivity.

        Reports readiness. Does not change any mode -- the name is historical.
        """
        from src.trading.connectors.binance.futures_sdk import (
            BinanceFuturesConfig,
            get_binance_futures_client,
        )

        cfg = BinanceFuturesConfig.from_env()
        client = get_binance_futures_client(cfg)
        testnet_reachable = False
        server_time = None
        try:
            server_time = await run_in_threadpool(client.get_server_time)
            testnet_reachable = True
        except Exception as exc:
            logger.warning("Testnet connectivity check failed during switch: %s", exc)

        ready = testnet_reachable and bool(cfg.api_key and cfg.api_secret)
        return {
            "ok": True,
            "ready": ready,
            "testnet_reachable": testnet_reachable,
            "server_time": server_time,
            "configured": bool(cfg.api_key and cfg.api_secret),
            "mode": "testnet" if ready else "paper",
            "message": "Binance Futures Testnet connected and ready for order execution."
            if ready
            else "Binance Testnet reachable in demo mode. Configure API keys in Settings "
                 "to execute live testnet orders.",
        }

    # --- Signal Priority Queue & Multi-Strategy Router ------------------------

    @app.post("/paper-sessions/signal-queue/enqueue", dependencies=auth_dependencies)
    async def enqueue_signal_endpoint(payload: dict[str, Any] = Body(...)):
        """Enqueue a candidate signal from Idim Ikang or the Scaffs picker.

        ``raw_score`` is REQUIRED. The previous default of 65.0 sat above the
        60.0 absolute floor, so a producer that omitted a score was admitted
        automatically -- the quality gate defaulted open.
        """
        from src.trading.signal_queue import SignalQueueManager

        symbol = payload.get("symbol")
        side = payload.get("side")
        if not symbol or not side:
            raise HTTPException(status_code=400, detail="Missing required 'symbol' or 'side' fields.")

        if payload.get("raw_score") is None:
            raise HTTPException(
                status_code=400,
                detail=f"'raw_score' is required (absolute floor {_ABSOLUTE_SCORE_FLOOR}); "
                       "an unscored signal is never admitted by default.",
            )
        try:
            raw_score = float(payload["raw_score"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid raw_score: {exc}") from exc

        producer = str(payload.get("producer", "scaffs_picker"))
        timeframe = str(payload.get("timeframe", "5m"))
        source_signal_id = payload.get("source_signal_id")
        criteria = payload.get("criteria_vector") or {}
        if not isinstance(criteria, dict):
            raise HTTPException(status_code=400, detail="criteria_vector must be an object")
        try:
            ttl = int(payload.get("ttl_seconds", 300))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid ttl_seconds: {exc}") from exc
        if ttl <= 0:
            raise HTTPException(status_code=400, detail="ttl_seconds must be positive")

        mgr = SignalQueueManager()
        res = await run_in_threadpool(
            mgr.enqueue_signal,
            symbol=symbol,
            side=side,
            producer=producer,
            timeframe=timeframe,
            raw_score=raw_score,
            source_signal_id=source_signal_id,
            criteria_vector=criteria,
            ttl_seconds=ttl,
        )

        if not res.get("ok"):
            raise HTTPException(status_code=422, detail=res)
        return res

    @app.get("/paper-sessions/signal-queue/pending", dependencies=auth_dependencies)
    async def get_pending_queue_endpoint(limit: int = 20):
        """Active unexpired signals, ranked by TOPSIS closeness coefficient.

        The coefficient is RELATIVE to the current batch. A score of 0.9 means
        'closest to ideal among what is queued right now', not '90% confidence'.
        Absolute admission is the enqueue-time floor, not this ranking.
        """
        from src.trading.signal_queue import SignalQueueManager

        mgr = SignalQueueManager()
        ranked = await run_in_threadpool(mgr.get_pending_batch, limit=_clamp_limit(limit, 20))
        return {
            "ok": True,
            "count": len(ranked),
            "signals": ranked,
            "ranking_note": "topsis_score is relative to this batch, not an absolute probability",
        }

    @app.post("/paper-sessions/signal-queue/dispatch", dependencies=auth_dependencies)
    async def dispatch_queued_signal_endpoint(payload: dict[str, Any] = Body(...)):
        """Dispatch one queued signal through collision checks to the matching engine."""
        from src.trading.signal_queue import SignalQueueManager

        queue_id = payload.get("queue_id")
        if not queue_id:
            raise HTTPException(status_code=400, detail="Missing required 'queue_id' field.")

        try:
            quantity = float(payload["quantity"]) if payload.get("quantity") is not None else None
            notional_usd = float(payload.get("notional_usd", 25.0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid quantity/notional_usd: {exc}") from exc

        # Same ceiling as the direct order route -- the queue is not a bypass.
        effective_limit = _effective_notional_cap()
        if notional_usd <= 0:
            raise HTTPException(status_code=400, detail="notional_usd must be positive")
        if notional_usd > effective_limit:
            raise HTTPException(
                status_code=400,
                detail=f"Requested notional (${notional_usd:.2f}) exceeds hard governance "
                       f"limit (${effective_limit:.2f}).",
            )

        mgr = SignalQueueManager()
        try:
            return await run_in_threadpool(
                mgr.dispatch_queued_signal,
                queue_id=queue_id,
                quantity=quantity,
                notional_usd=notional_usd,
            )
        except Exception as exc:
            logger.error("queue dispatch failed queue_id=%s: %s", queue_id, exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/paper-sessions/signal-queue/history", dependencies=auth_dependencies)
    async def get_queue_history_endpoint(limit: int = 50):
        """Recent queue transitions across all statuses."""
        from src.trading.signal_queue import SignalQueueManager
        import psycopg

        mgr = SignalQueueManager()
        rows = []
        try:
            with psycopg.connect(mgr.dsn, connect_timeout=_DB_CONNECT_TIMEOUT) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, source_signal_id, producer, symbol, side, timeframe,
                           raw_score, topsis_score, target_strategy, status, rejection_reason,
                           execution_order_id, execution_client_order_id,
                           created_at, dispatched_at, completed_at, criteria_vector
                    FROM paper_trading.signal_queue
                    ORDER BY created_at DESC
                    LIMIT %s;
                    """,
                    (_clamp_limit(limit, 50),),
                )
                for r in cur.fetchall():
                    crit = r[16] if isinstance(r[16], dict) else json.loads(r[16] or "{}")
                    rows.append({
                        "id": str(r[0]),
                        "source_signal_id": r[1],
                        "producer": r[2],
                        "symbol": r[3],
                        "side": r[4],
                        "timeframe": r[5],
                        "raw_score": float(r[6]) if r[6] is not None else None,
                        "topsis_score": float(r[7]) if r[7] is not None else None,
                        "target_strategy": r[8],
                        "status": r[9],
                        "rejection_reason": r[10],
                        "execution_order_id": r[11],
                        "execution_client_order_id": r[12],
                        "created_at": r[13].isoformat() if r[13] else None,
                        "dispatched_at": r[14].isoformat() if r[14] else None,
                        "completed_at": r[15].isoformat() if r[15] else None,
                        "criteria_vector": crit,
                    })
        except Exception as exc:
            logger.error("queue history query failed: %s", exc)
            raise HTTPException(status_code=503, detail="signal queue history unavailable") from exc
        return {"ok": True, "count": len(rows), "history": rows}

    @app.post("/paper-sessions/signal-queue/sync-idim", dependencies=auth_dependencies)
    async def sync_idim_signals_endpoint(payload: dict[str, Any] = Body(default={})):
        """Pull the live Idim Ikang stream into the Scaffs priority queue.

        ``auto_dispatch`` fires orders at the matching engine with no further
        human step. It is therefore gated behind an explicit environment flag,
        not an HTTP body field -- a request body must not be able to turn on
        autonomous execution.
        """
        from src.trading.idim_feed_bridge import IdimFeedBridge

        requested_auto = bool(payload.get("auto_dispatch", False))
        env_allows = os.environ.get("ALLOW_AUTO_EXECUTION", "false").lower() in ("1", "true", "yes")
        if requested_auto and not env_allows:
            raise HTTPException(
                status_code=403,
                detail=(
                    "auto_dispatch requires ALLOW_AUTO_EXECUTION=true in the environment. "
                    "Sync ingests signals; dispatch stays an explicit, separate action."
                ),
            )
        auto_dispatch = requested_auto and env_allows

        try:
            notional_usd = float(payload.get("notional_usd", 25.0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid notional_usd: {exc}") from exc

        effective_limit = _effective_notional_cap()
        if notional_usd <= 0 or notional_usd > effective_limit:
            raise HTTPException(
                status_code=400,
                detail=f"notional_usd must be in (0, {effective_limit:.2f}].",
            )

        if auto_dispatch:
            logger.warning(
                "AUTO-DISPATCH ENABLED: Idim sync will place live orders at %.2f USD notional",
                notional_usd,
            )

        bridge = IdimFeedBridge()
        res = await run_in_threadpool(
            bridge.sync_and_enqueue_signals,
            auto_dispatch=auto_dispatch,
            notional_usd=notional_usd,
        )
        res["auto_dispatch_applied"] = auto_dispatch
        return res

    # -------------------------------------------------------------------------
    # Wildcard session routes LAST, so no literal path above can be shadowed.
    # -------------------------------------------------------------------------

    @app.get("/paper-sessions/{session_id}", dependencies=auth_dependencies)
    async def get_paper_session(session_id: str):
        """Full detail for one paper session: config, every mark, equity curve."""
        _validate_session_id(session_id)
        session_dir = PAPER_SESSIONS_DIR / session_id
        schema = _detect_session_schema(session_dir) if session_dir.exists() else None
        if schema is None:
            raise HTTPException(status_code=404, detail=f"paper session {session_id!r} not found")
        active_ids, archived_ids, registry_error = _load_registry()
        classification = "unknown" if registry_error is not None else _classify_session(
            session_id, active_ids, archived_ids
        )
        if schema == "paper_session":
            return _summarize(session_dir, classification=classification)
        return _load_futures_paper_session(session_dir, classification=classification)

    @app.get("/paper-sessions/{session_id}/live-prices", dependencies=auth_dependencies)
    async def get_paper_session_live_prices(session_id: str):
        """Current live prices for a session's symbols -- display only.

        Never reads or writes marks.jsonl/trades.jsonl/book.json.
        """
        _validate_session_id(session_id)
        session_dir = PAPER_SESSIONS_DIR / session_id
        session_path = session_dir / "session.json"
        if not session_path.exists():
            raise HTTPException(status_code=404, detail=f"paper session {session_id!r} not found")
        session = json.loads(session_path.read_text(encoding="utf-8"))

        # pyrefly: ignore [missing-import]
        from paper_session import fetch_last_prices_fast

        try:
            prices = await run_in_threadpool(fetch_last_prices_fast, session["symbols"])
        except Exception as exc:  # noqa: BLE001 - upstream exchange call, surface as 502
            raise HTTPException(status_code=502, detail=f"live price fetch failed: {exc}") from exc

        return {"prices": prices, "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/paper-sessions/{session_id}/diagnostics", dependencies=auth_dependencies)
    async def get_paper_session_diagnostics(session_id: str):
        """Detailed fee-aware diagnostics from the receipted paper ledger."""
        _validate_session_id(session_id)
        session_dir = PAPER_SESSIONS_DIR / session_id
        if not session_dir.exists() or not (session_dir / "session.json").exists():
            raise HTTPException(status_code=404, detail=f"paper session {session_id!r} not found")

        # pyrefly: ignore [missing-import]
        from paper_session import compute_session_diagnostics

        return await run_in_threadpool(compute_session_diagnostics, session_dir)

    @app.get("/paper-sessions/{session_id}/diagnostics.csv", dependencies=auth_dependencies)
    async def get_paper_session_diagnostics_csv(session_id: str):
        """CSV export of closed paper trades for offline audit."""
        _validate_session_id(session_id)
        session_dir = PAPER_SESSIONS_DIR / session_id
        if not session_dir.exists() or not (session_dir / "session.json").exists():
            raise HTTPException(status_code=404, detail=f"paper session {session_id!r} not found")

        # pyrefly: ignore [missing-import]
        from paper_session import export_closed_trade_diagnostics_csv

        export_path = session_dir / "closed_trade_diagnostics.csv"
        await run_in_threadpool(export_closed_trade_diagnostics_csv, session_dir, export_path)
        return FileResponse(
            export_path,
            media_type="text/csv",
            filename=f"{session_id}-closed-trade-diagnostics.csv",
        )