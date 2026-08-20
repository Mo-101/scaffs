#!/usr/bin/env python3
"""Replay driver: strategy intent -> real engine -> real ledger -> DTO.

This is the only place that decides *what to trade*.  It never computes a P&L
number.  It hands order intents to ``futures_paper_engine`` and lets the engine
produce fills, fees, funding, liquidations and closed trades; the resulting
ledger is then rendered by ``dto.build_session_dto``.

        strategy signal
              |
              v
        engine.open_position          <- fees charged here
              |
        engine.process_all(prices)    <- TP / SL / liquidation checked here
              |
        engine.apply_funding          <- only at real settlement timestamps
              |
        account.json + trades.jsonl + marks.jsonl
              |
              v
        build_session_dto  ->  metrics  ->  dashboard

Price provenance
----------------
Prices default to a deterministic seeded GBM path so a run is reproducible
offline.  That makes the *market* synthetic while the *accounting* is real, and
the DTO says so: ``market_source`` is ``"synthetic_gbm"``, not ``"okx"``.  Point
``--marks`` at a JSONL file of real observed prices to replay a genuine path.

Simulated clock
---------------
The engine stamps events with ``utc_now()``.  For a replay we need the ledger to
carry the simulated timestamps, so the driver swaps that module attribute for a
clock it controls.  This is why the equity series has honest 15-minute spacing
instead of everything landing inside one wall-clock second.

Known engine gap: ``process_price`` reads ``datetime.now(timezone.utc)``
directly for the ``max_hold`` check rather than going through ``utc_now()``, so
max-hold exits cannot be replayed.  The driver leaves ``max_hold_minutes`` unset
and relies on TP/SL/liquidation until that is fixed in the engine.

stdlib only.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "backend" / "agent") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "backend" / "agent"))

import futures_paper_engine as fpe  # noqa: E402

from . import metrics as M  # noqa: E402
from .dto import SessionMeta, build_session_dto  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "out"
SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"

FUNDING_INTERVAL_HOURS = 8
TICK_SECONDS = 15 * 60          # one engine tick == one 15m bar
DEFAULT_DAYS = 14


class SimClock:
    """A clock the replay controls, substituted for the engine's ``utc_now``."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def iso(self) -> str:
        return self.now.isoformat()

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass(slots=True)
class SymbolSpec:
    """Price-path parameters for one instrument."""

    symbol: str
    start_price: float
    annual_drift: float = 0.0
    annual_vol: float = 0.65
    funding_annual_bias: float = 0.0    # signed; drives the 8h funding rate


@dataclass(slots=True)
class StrategySpec:
    """Everything the optimizer will eventually search over."""

    session_id: str
    strategy_id: str
    leverage: int = 5
    margin: float = 50.0
    take_profit_pct: float = 0.012
    stop_loss_pct: float = 0.006
    trailing_stop_pct: Optional[float] = None
    entry_zscore: float = 1.6           # |z| beyond which we take a position
    lookback: int = 32                  # bars in the mean-reversion window
    max_concurrent: int = 3
    initial_balance: float = 5_000.0
    timeframe: str = "15m"
    symbols: tuple[SymbolSpec, ...] = ()
    notes: str = ""


def gbm_path(spec: SymbolSpec, bars: int, seconds_per_bar: float, rng: random.Random) -> list[float]:
    """Geometric Brownian motion sampled at the bar interval.

    Deterministic given the seed, so a strategy comparison is a comparison of
    strategies rather than of luck.
    """
    dt = seconds_per_bar / M.SECONDS_PER_YEAR
    drift = (spec.annual_drift - 0.5 * spec.annual_vol ** 2) * dt
    shock = spec.annual_vol * math.sqrt(dt)
    price = spec.start_price
    out = [price]
    for _ in range(bars):
        price *= math.exp(drift + shock * rng.gauss(0.0, 1.0))
        out.append(price)
    return out


def funding_rate_for(spec: SymbolSpec, rng: random.Random) -> float:
    """An 8h funding rate: a per-symbol bias plus noise, in decimal form."""
    return spec.funding_annual_bias / (365 * 24 / FUNDING_INTERVAL_HOURS) + rng.gauss(0.0, 0.00004)


def zscore(window: list[float]) -> Optional[float]:
    if len(window) < 8:
        return None
    mean = sum(window) / len(window)
    var = sum((v - mean) ** 2 for v in window) / (len(window) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return None
    return (window[-1] - mean) / sd


@dataclass(slots=True)
class ReplayResult:
    session_id: str
    session_dir: Path
    dto: dict[str, Any]
    bars: int
    opened: int
    closed: int


def run_replay(
    strategy: StrategySpec,
    *,
    days: int = DEFAULT_DAYS,
    seed: int = 7,
    start: Optional[datetime] = None,
    sessions_dir: Path = SESSIONS_DIR,
    fresh: bool = True,
) -> ReplayResult:
    """Run one strategy through the real engine and return its session DTO."""
    bars = int(days * 24 * 3600 / TICK_SECONDS)
    start = start or (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0)
    clock = SimClock(start)

    session_dir = sessions_dir / strategy.session_id
    if fresh and session_dir.exists():
        shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    price_rng = random.Random(seed)
    funding_rng = random.Random(seed + 1)
    paths = {s.symbol: gbm_path(s, bars, TICK_SECONDS, price_rng) for s in strategy.symbols}
    # Positions come back carrying the engine's normalized symbol ("BTCUSDT"),
    # so index the specs the same way rather than by the display form.
    specs = {fpe.normalize_symbol(s.symbol): s for s in strategy.symbols}

    # The engine timestamps everything through this module attribute; pointing
    # it at the simulated clock is what makes the ledger replayable.
    original_utc_now = fpe.utc_now
    fpe.utc_now = clock.iso  # type: ignore[assignment]

    opened = 0
    closed_count = 0
    try:
        engine = fpe.FuturesPaperEngine(
            session_dir,
            initial_balance=strategy.initial_balance,
            acquire_lock=False,
        )
        risk = fpe.RiskConfig(
            margin_mode="isolated",
            leverage=strategy.leverage,
            margin=strategy.margin,
            take_profit_pct=strategy.take_profit_pct,
            stop_loss_pct=strategy.stop_loss_pct,
            trailing_stop_pct=strategy.trailing_stop_pct,
            max_hold_minutes=None,   # see module docstring: not replayable yet
            entry_order_type="taker",
            exit_order_type="taker",
        )
        risk.validate()

        history: dict[str, list[float]] = {fpe.normalize_symbol(s.symbol): [] for s in strategy.symbols}
        last_funding_index = -1

        for i in range(bars + 1):
            prices = {fpe.normalize_symbol(sym): path[i] for sym, path in paths.items()}
            for sym, px in prices.items():
                history[sym].append(px)
                if len(history[sym]) > strategy.lookback:
                    history[sym].pop(0)

            # 1. Let the engine resolve exits first: TP / SL / liquidation are
            #    engine events, and this call also writes the equity snapshot.
            closed_count += len(engine.process_all(prices, market_data_source="synthetic_gbm"))

            # 2. Funding settles only on real 8h boundaries, only for positions
            #    that actually exist at that timestamp, and idempotently.
            hours = (clock.now - start).total_seconds() / 3600.0
            funding_index = int(hours // FUNDING_INTERVAL_HOURS)
            if funding_index > last_funding_index and funding_index > 0:
                last_funding_index = funding_index
                window = (start + timedelta(hours=funding_index * FUNDING_INTERVAL_HOURS)).isoformat()
                for trade_id, pos in list(engine.state.positions.items()):
                    rate = funding_rate_for(specs[pos.symbol], funding_rng)
                    engine.apply_funding(
                        trade_id,
                        rate,
                        price=prices[pos.symbol],
                        funding_time=window,
                        event_id=f"{pos.symbol}:{window}",
                    )

            # 3. Strategy intent. Mean reversion: fade stretched prices.
            if len(engine.state.positions) < strategy.max_concurrent:
                held = {p.symbol for p in engine.state.positions.values()}
                for sym in sorted(prices):
                    if sym in held or len(engine.state.positions) >= strategy.max_concurrent:
                        continue
                    z = zscore(history[sym])
                    if z is None or abs(z) < strategy.entry_zscore:
                        continue
                    side = "short" if z > 0 else "long"
                    try:
                        engine.open_position(
                            sym,
                            side,
                            price=prices[sym],
                            risk=risk,
                            signal_reason=f"mean_reversion_z={z:.2f}",
                            market_regime="ranging" if abs(z) < 2.5 else "stretched",
                        )
                        opened += 1
                    except RuntimeError:
                        # Insufficient available balance: a real constraint, not
                        # an error to paper over.
                        break

            clock.advance(TICK_SECONDS)

        final_prices = {sym: path[bars] for sym, path in paths.items()}
        snapshot = engine.snapshot(final_prices)
        meta = SessionMeta(
            session_id=strategy.session_id,
            strategy_id=strategy.strategy_id,
            worker_id=strategy.session_id,
            timeframe=strategy.timeframe,
            symbols=tuple(sorted(paths)),
            leverage=strategy.leverage,
            market_source="synthetic_gbm",
            notes=strategy.notes,
        )
        dto = build_session_dto(session_dir, meta, snapshot=snapshot)
    finally:
        fpe.utc_now = original_utc_now  # type: ignore[assignment]

    return ReplayResult(
        session_id=strategy.session_id,
        session_dir=session_dir,
        dto=dto,
        bars=bars,
        opened=opened,
        closed=closed_count,
    )


# --- default strategy roster -------------------------------------------------

MAJORS = (
    SymbolSpec("BTC-USDT", 96_420.50, annual_drift=0.35, annual_vol=0.55, funding_annual_bias=0.11),
    SymbolSpec("ETH-USDT", 2_745.80, annual_drift=0.20, annual_vol=0.70, funding_annual_bias=0.09),
    SymbolSpec("SOL-USDT", 188.60, annual_drift=0.10, annual_vol=0.95, funding_annual_bias=0.49),
)


def default_roster() -> list[StrategySpec]:
    """The comparison set: same market path, different parameters.

    Deliberately small.  These are candidates to be measured, not a claim that
    any of them has an edge.
    """
    return [
        StrategySpec(
            session_id="mr_5x_tight",
            strategy_id="mean_reversion_v1",
            leverage=5, margin=50.0,
            take_profit_pct=0.012, stop_loss_pct=0.006,
            entry_zscore=1.6, symbols=MAJORS,
            notes="5x, 2:1 reward:risk, z>1.6",
        ),
        StrategySpec(
            session_id="mr_10x_tight",
            strategy_id="mean_reversion_v1",
            leverage=10, margin=50.0,
            take_profit_pct=0.012, stop_loss_pct=0.006,
            entry_zscore=1.6, symbols=MAJORS,
            notes="same signal as mr_5x_tight at 10x -- isolates leverage",
        ),
        StrategySpec(
            session_id="mr_5x_wide",
            strategy_id="mean_reversion_v1",
            leverage=5, margin=50.0,
            take_profit_pct=0.024, stop_loss_pct=0.012,
            entry_zscore=2.2, symbols=MAJORS,
            notes="wider bands, more selective entries",
        ),
        StrategySpec(
            session_id="mr_5x_trailing",
            strategy_id="mean_reversion_v1",
            leverage=5, margin=50.0,
            take_profit_pct=0.020, stop_loss_pct=0.010,
            trailing_stop_pct=0.006, entry_zscore=1.8, symbols=MAJORS,
            notes="trailing stop variant",
        ),
    ]


def write_outputs(results: list[ReplayResult], output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for r in results:
        (output_dir / f"{r.session_id}.json").write_text(
            json.dumps(r.dto, indent=2), encoding="utf-8"
        )
        risk = r.dto["metrics"]["risk"]
        stats = r.dto["metrics"]["trade_stats"]
        index.append({
            "session_id": r.session_id,
            "mode": "paper_engine",
            "strategy_id": r.dto["session"]["strategy_id"],
            "leverage": r.dto["session"]["leverage"],
            "updated_at": r.dto["updated_at"],
            "starting_equity": r.dto["starting_equity"],
            "current_equity": r.dto["current_equity"],
            "net_pnl": r.dto["net_pnl"],
            "account_return": r.dto["account_return"],
            "closed_trades": stats["closed_trades"],
            "win_rate": stats["win_rate"],
            "profit_factor": stats["profit_factor"],
            "liquidations": stats["liquidations"],
            "sharpe": risk["sharpe"],
            "sharpe_status": risk["sharpe_status"],
            "max_drawdown": risk["max_drawdown"],
            "calmar": risk["calmar"],
            "calmar_status": risk["calmar_status"],
        })
    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps({
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "paper_engine",
            "sessions": index,
        }, indent=2),
        encoding="utf-8",
    )
    return index_path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    results = [run_replay(s, days=args.days, seed=args.seed) for s in default_roster()]
    index_path = write_outputs(results, args.output)

    print(f"{'session':<16} {'trades':>7} {'net P&L':>10} {'return':>8} "
          f"{'maxDD':>7} {'sharpe':>9} {'liq':>4}")
    for r in results:
        risk = r.dto["metrics"]["risk"]
        stats = r.dto["metrics"]["trade_stats"]
        sharpe = f"{risk['sharpe']:.2f}" if risk["sharpe"] is not None else risk["sharpe_status"][:9]
        mdd = f"{risk['max_drawdown'] * 100:.2f}%" if risk["max_drawdown"] is not None else "n/a"
        ret = f"{r.dto['account_return'] * 100:.2f}%" if r.dto["account_return"] is not None else "n/a"
        print(f"{r.session_id:<16} {stats['closed_trades']:>7} "
              f"{r.dto['net_pnl']:>10.2f} {ret:>8} {mdd:>7} {sharpe:>9} "
              f"{stats['liquidations']:>4}")
    print(f"\nwrote {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
