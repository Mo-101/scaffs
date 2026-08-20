#!/usr/bin/env python3
"""Ledger-derived performance metrics.

Every number here is computed from two inputs and nothing else:

  * ``closed_trades`` -- the immutable closed-trade ledger written by
    ``futures_paper_engine.close_position``
  * ``equity_points`` -- timestamped equity snapshots

There are no constants, no fixtures and no fallbacks that invent a plausible
number when the data is thin.  When a statistic is not yet supportable the
result is ``None`` plus a machine-readable ``*_status`` reason, and the UI is
expected to render "N/A" rather than a confident-looking figure.

The load-bearing property is **sampling-rate invariance**: returns are computed
on a fixed wall-clock grid re-sampled from the equity snapshots, so changing how
often the dashboard polls (or how often the driver snapshots) cannot move
Sharpe, Sortino, volatility or drawdown.  ``tests/test_metrics.py`` asserts it.

stdlib only -- this module must import on a bare python3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal, Optional, Sequence

SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0

# Re-sampling grid for return-based statistics.  15 minutes matches the
# timeframe the workers actually trade on; periods_per_year is derived from it
# rather than hardcoded, so changing the interval stays self-consistent.
DEFAULT_RESAMPLE_SECONDS = 15 * 60

# Gates below which a statistic is reported as unavailable instead of estimated.
MIN_RETURN_SAMPLES = 30                              # ~7.5h of 15m bars
MIN_SESSION_SECONDS_FOR_ANNUALIZED = 24 * 60 * 60    # 1 day before we annualize
MIN_CLOSED_TRADES_FOR_STATS = 1

MetricStatus = Literal[
    "ok",
    "insufficient_samples",
    "insufficient_duration",
    "no_closed_trades",
    "undefined",
]


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class EquityPoint:
    """One timestamped equity observation. ``equity`` is total account value."""

    timestamp: datetime
    equity: float

    @classmethod
    def parse(cls, raw: Any) -> "EquityPoint":
        if isinstance(raw, EquityPoint):
            return raw
        return cls(timestamp=_parse_ts(raw["timestamp"]), equity=float(raw["equity"]))


def resample_equity(
    points: Sequence[EquityPoint],
    interval_seconds: int = DEFAULT_RESAMPLE_SECONDS,
) -> list[EquityPoint]:
    """Project irregular equity snapshots onto a fixed wall-clock grid.

    Uses last-observation-carried-forward, the correct convention for a running
    balance: between snapshots the account's recorded equity is the last one
    observed.  Grid timestamps are anchored to the first observation so the
    output does not depend on when the process started relative to the clock.

    This is the function that makes the metrics polling-rate invariant: two runs
    observing the same underlying equity path at different snapshot frequencies
    resample onto the same grid.
    """
    ordered = sorted(points, key=lambda p: p.timestamp)
    if len(ordered) < 2 or interval_seconds <= 0:
        return list(ordered)

    step = timedelta(seconds=interval_seconds)
    start, end = ordered[0].timestamp, ordered[-1].timestamp
    grid: list[EquityPoint] = []
    idx = 0
    cursor = start
    last_equity = ordered[0].equity

    while cursor <= end:
        while idx < len(ordered) and ordered[idx].timestamp <= cursor:
            last_equity = ordered[idx].equity
            idx += 1
        grid.append(EquityPoint(timestamp=cursor, equity=last_equity))
        cursor += step

    # A trailing partial bar is deliberately dropped rather than carried. Its
    # return would cover less wall-clock time than every other sample, so
    # including it makes the statistics depend on exactly when observation
    # stopped -- which is the sampling-rate leak this function exists to close.
    # Drawdown and total return are computed on the raw points, so nothing that
    # needs the final observation loses it.
    return grid


def simple_returns(points: Sequence[EquityPoint]) -> list[float]:
    """Period-over-period fractional returns, skipping non-positive equity."""
    out: list[float] = []
    for prev, cur in zip(points, points[1:]):
        if prev.equity > 0:
            out.append(cur.equity / prev.equity - 1.0)
    return out


def _sample_std(values: Sequence[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def max_drawdown(points: Sequence[EquityPoint]) -> Optional[float]:
    """Peak-to-trough decline of the equity curve, as a positive fraction.

    Returns ``None`` (not 0.0) when there is no curve to measure -- an unknown
    drawdown and a genuinely flat one are different facts.
    """
    ordered = sorted(points, key=lambda p: p.timestamp)
    if len(ordered) < 2:
        return None
    peak = ordered[0].equity
    worst = 0.0
    for p in ordered:
        if p.equity > peak:
            peak = p.equity
        if peak > 0:
            worst = min(worst, p.equity / peak - 1.0)
    return abs(worst)


def cvar(returns: Sequence[float], confidence: float = 0.95) -> Optional[float]:
    """Expected shortfall: mean of losses at or beyond the VaR threshold.

    Reported as a positive number representing a loss.  Grid strategies die in
    the tail, so this is a first-class constraint rather than a footnote.
    """
    if len(returns) < MIN_RETURN_SAMPLES:
        return None
    ordered = sorted(returns)
    cutoff = max(1, int(round((1.0 - confidence) * len(ordered))))
    tail = ordered[:cutoff]
    if not tail:
        return None
    return abs(sum(tail) / len(tail))


@dataclass(slots=True)
class TradeStats:
    """Closed-trade statistics. Every field is a count or a mean over the ledger."""

    closed_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    largest_win: Optional[float] = None
    largest_loss: Optional[float] = None
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: Optional[float] = None
    realized_net_pnl: float = 0.0
    total_fees: float = 0.0
    total_funding: float = 0.0
    total_liquidation_fees: float = 0.0
    liquidations: int = 0
    status: MetricStatus = "no_closed_trades"

    def to_dict(self) -> dict[str, Any]:
        return {
            "closed_trades": self.closed_trades,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "breakeven_count": self.breakeven_count,
            "win_rate": self.win_rate,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "profit_factor": self.profit_factor,
            "realized_net_pnl": self.realized_net_pnl,
            "total_fees": self.total_fees,
            "total_funding": self.total_funding,
            "total_liquidation_fees": self.total_liquidation_fees,
            "liquidations": self.liquidations,
            "status": self.status,
        }


def compute_trade_stats(closed_trades: Iterable[dict[str, Any]]) -> TradeStats:
    """Derive every closed-trade statistic from the ledger rows themselves.

    ``net_pnl`` on an engine ClosedTrade is already net of entry fee, exit fee,
    accrued funding and any liquidation fee (see
    ``futures_paper_engine.close_position``).  Fees and funding are therefore
    reported here as *attribution* of that figure -- subtracting them again
    downstream would double-count them.
    """
    rows = list(closed_trades)
    stats = TradeStats()
    if len(rows) < MIN_CLOSED_TRADES_FOR_STATS:
        return stats

    nets = [float(r["net_pnl"]) for r in rows]
    wins = [v for v in nets if v > 0]
    losses = [v for v in nets if v < 0]

    stats.closed_trades = len(rows)
    stats.win_count = len(wins)
    stats.loss_count = len(losses)
    stats.breakeven_count = len(nets) - len(wins) - len(losses)
    stats.win_rate = len(wins) / len(nets)
    stats.avg_win = (sum(wins) / len(wins)) if wins else None
    stats.avg_loss = abs(sum(losses) / len(losses)) if losses else None
    stats.largest_win = max(wins) if wins else None
    stats.largest_loss = min(losses) if losses else None
    stats.gross_profit = sum(wins)
    stats.gross_loss = abs(sum(losses))
    # Undefined rather than a flattering constant when nothing has lost yet.
    stats.profit_factor = (stats.gross_profit / stats.gross_loss) if stats.gross_loss > 0 else None
    stats.realized_net_pnl = sum(nets)
    stats.total_fees = sum(float(r.get("entry_fee", 0.0)) + float(r.get("exit_fee", 0.0)) for r in rows)
    stats.total_funding = sum(float(r.get("funding_paid", 0.0)) for r in rows)
    stats.total_liquidation_fees = sum(float(r.get("liquidation_fee", 0.0)) for r in rows)
    stats.liquidations = sum(1 for r in rows if r.get("exit_reason") == "liquidation")
    stats.status = "ok"
    return stats


@dataclass(slots=True)
class RiskMetrics:
    """Return-based risk statistics, each with an explicit availability status."""

    resample_seconds: int = DEFAULT_RESAMPLE_SECONDS
    periods_per_year: float = 0.0
    sample_count: int = 0
    session_seconds: float = 0.0
    period_return_mean: Optional[float] = None
    period_return_std: Optional[float] = None
    annualized_return: Optional[float] = None
    annualized_volatility: Optional[float] = None
    downside_deviation: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    max_drawdown: Optional[float] = None
    cvar_95: Optional[float] = None
    total_return: Optional[float] = None
    sharpe_status: MetricStatus = "insufficient_samples"
    calmar_status: MetricStatus = "insufficient_duration"
    annualization_status: MetricStatus = "insufficient_duration"

    def to_dict(self) -> dict[str, Any]:
        return {
            "resample_seconds": self.resample_seconds,
            "periods_per_year": self.periods_per_year,
            "sample_count": self.sample_count,
            "session_seconds": self.session_seconds,
            "period_return_mean": self.period_return_mean,
            "period_return_std": self.period_return_std,
            "annualized_return": self.annualized_return,
            "annualized_volatility": self.annualized_volatility,
            "downside_deviation": self.downside_deviation,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "max_drawdown": self.max_drawdown,
            "cvar_95": self.cvar_95,
            "total_return": self.total_return,
            "sharpe_status": self.sharpe_status,
            "calmar_status": self.calmar_status,
            "annualization_status": self.annualization_status,
        }


def compute_risk_metrics(
    equity_points: Sequence[Any],
    *,
    resample_seconds: int = DEFAULT_RESAMPLE_SECONDS,
    risk_free_annual: float = 0.0,
    min_samples: int = MIN_RETURN_SAMPLES,
    min_seconds_for_annualized: float = MIN_SESSION_SECONDS_FOR_ANNUALIZED,
) -> RiskMetrics:
    """Sharpe/Sortino/Calmar/drawdown from a timestamped equity series.

    The annualization factor is derived from ``resample_seconds`` -- it is not a
    magic 187.18 applied to whatever samples happen to exist.  A session that
    has not run long enough to annualize honestly reports ``None`` with an
    ``insufficient_duration`` status instead of scaling minutes of noise up to a
    yearly figure.
    """
    points = [EquityPoint.parse(p) for p in equity_points]
    periods_per_year = SECONDS_PER_YEAR / float(resample_seconds)
    out = RiskMetrics(resample_seconds=resample_seconds, periods_per_year=periods_per_year)

    if len(points) < 2:
        return out

    points.sort(key=lambda p: p.timestamp)
    out.session_seconds = (points[-1].timestamp - points[0].timestamp).total_seconds()
    if points[0].equity > 0:
        out.total_return = points[-1].equity / points[0].equity - 1.0

    # Drawdown is measured on the raw observations: it is a path property, and
    # re-sampling could step over the actual trough.
    out.max_drawdown = max_drawdown(points)

    grid = resample_equity(points, resample_seconds)
    returns = simple_returns(grid)
    out.sample_count = len(returns)

    if len(returns) < min_samples:
        out.sharpe_status = "insufficient_samples"
        out.calmar_status = "insufficient_samples"
        out.annualization_status = "insufficient_samples"
        return out

    rf_period = risk_free_annual / periods_per_year
    excess = [r - rf_period for r in returns]
    mean = sum(excess) / len(excess)
    std = _sample_std(excess, mean)
    downside = math.sqrt(sum(min(0.0, r) ** 2 for r in excess) / len(excess))

    out.period_return_mean = mean
    out.period_return_std = std
    out.cvar_95 = cvar(returns)

    sqrt_ppy = math.sqrt(periods_per_year)
    if std > 0:
        out.sharpe = (mean / std) * sqrt_ppy
        out.sharpe_status = "ok"
    else:
        out.sharpe_status = "undefined"
    if downside > 0:
        out.sortino = (mean / downside) * sqrt_ppy
    out.annualized_volatility = std * sqrt_ppy
    out.downside_deviation = downside * sqrt_ppy

    if out.session_seconds >= min_seconds_for_annualized:
        out.annualization_status = "ok"
        mean_total = sum(returns) / len(returns)
        out.annualized_return = (1.0 + mean_total) ** periods_per_year - 1.0
        if out.max_drawdown and out.max_drawdown > 0:
            out.calmar = out.annualized_return / out.max_drawdown
            out.calmar_status = "ok"
        else:
            out.calmar_status = "undefined"
    else:
        out.annualization_status = "insufficient_duration"
        out.calmar_status = "insufficient_duration"

    return out


def annualized_run_rate(
    net_profit: float,
    average_capital: float,
    elapsed_seconds: float,
    *,
    min_seconds: float = MIN_SESSION_SECONDS_FOR_ANNUALIZED,
) -> tuple[Optional[float], MetricStatus]:
    """Simple (non-compounded) annualized rate, gated on observation length.

    Returned alongside a status so the UI can label a short observation an
    "annualized run-rate" rather than an APR.  Bybit's displayed Grid APR floors
    a sub-24h run at one day, which is fine for platform parity but is not a
    quantity anything should be optimized against.
    """
    if average_capital <= 0 or elapsed_seconds <= 0:
        return None, "undefined"
    rate = (net_profit / average_capital) * (SECONDS_PER_YEAR / elapsed_seconds)
    if elapsed_seconds < min_seconds:
        return rate, "insufficient_duration"
    return rate, "ok"
