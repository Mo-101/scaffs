"""Master Service Supervisor for Scaffs Paper Trading.

Initializes retained paper sessions and runs continuous worker loops for:
1. Rebalance Equal Weight (rebalance_equal_weight_v1)
2. Grid Futures 5x (grid_futures_5x_v3)
3. Grid Futures 10x (grid_futures_10x_v3)
4. Morning Glory Funding Rate Z-score (morning_glory_futures)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure paths
AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(AGENT_DIR / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scaffs.services")

from paper_session import (
    _update_heartbeat,
    mark_once,
    rebalance_if_due,
    funding_rebalance_if_due,
    start_session,
    start_funding_session,
    _default_risk_config,
)

BASE_SESSIONS_DIR = AGENT_DIR / "paper_sessions"
SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT"]
DEFAULT_CASH = 10000.0


def initialize_all_sessions() -> None:
    """Ensure retained session directories and metadata exist."""
    BASE_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Verifying/initializing retained paper trading sessions in %s", BASE_SESSIONS_DIR)

    # 1. Grid Futures 5x (short rebalance interval for autonomous test)
    grid_5x_dir = BASE_SESSIONS_DIR / "grid_futures_5x_v3"
    if not (grid_5x_dir / "session.json").exists():
        try:
            start_session(
                grid_5x_dir,
                symbols=SYMBOLS,
                initial_cash=DEFAULT_CASH,
                rebalance_interval_hours=0.02,
                fee_rate=0.0005,
                min_rebalance_notional=0.1,
                risk_config=_default_risk_config(leverage=5.0, margin_mode="isolated"),
            )
            logger.info("Initialized grid_futures_5x_v3")
        except Exception as e:
            logger.warning("grid_futures_5x_v3 initialization note: %s", e)

    # 2. Grid Futures 10x (short rebalance interval for autonomous test)
    grid_10x_dir = BASE_SESSIONS_DIR / "grid_futures_10x_v3"
    if not (grid_10x_dir / "session.json").exists():
        try:
            start_session(
                grid_10x_dir,
                symbols=SYMBOLS,
                initial_cash=DEFAULT_CASH,
                rebalance_interval_hours=0.02,
                fee_rate=0.0005,
                min_rebalance_notional=0.1,
                risk_config=_default_risk_config(leverage=10.0, margin_mode="isolated"),
            )
            logger.info("Initialized grid_futures_10x_v3")
        except Exception as e:
            logger.warning("grid_futures_10x_v3 initialization note: %s", e)

    # 3. Morning Glory Funding Rate Z-score
    morning_glory_dir = BASE_SESSIONS_DIR / "morning_glory_futures"
    if not (morning_glory_dir / "session.json").exists():
        try:
            start_funding_session(
                morning_glory_dir,
                symbols=SYMBOLS,
                initial_cash=DEFAULT_CASH,
                z_window=120,
                entry_z=1.5,
                exit_z=0.5,
                fee_rate=0.0005,
                poll_seconds=60,
                risk_config=_default_risk_config(leverage=5.0, margin_mode="isolated"),
            )
            logger.info("Initialized morning_glory_futures")
        except Exception as e:
            logger.warning("morning_glory_futures initialization note: %s", e)

    # 4. Equal-Weight Rebalance
    rebalance_dir = BASE_SESSIONS_DIR / "rebalance_equal_weight_v1"
    if not (rebalance_dir / "session.json").exists():
        try:
            start_session(
                rebalance_dir,
                symbols=SYMBOLS,
                initial_cash=DEFAULT_CASH,
                rebalance_interval_hours=1.0,
                fee_rate=0.0005,
                min_rebalance_notional=0.1,
                risk_config=_default_risk_config(leverage=5.0, margin_mode="isolated"),
            )
            logger.info("Initialized rebalance_equal_weight_v1")
        except Exception as e:
            logger.warning("rebalance_equal_weight_v1 initialization note: %s", e)


def run_session_worker(session_name: str, is_funding: bool = False, poll_interval_sec: int = 30) -> None:
    """Continuous worker loop for one session."""
    session_dir = BASE_SESSIONS_DIR / session_name
    logger.info("Worker started for session: %s (interval=%ds)", session_name, poll_interval_sec)

    while True:
        try:
            _update_heartbeat(session_dir)
            if is_funding:
                res = funding_rebalance_if_due(session_dir)
                if res is None:
                    mark_once(session_dir)
            else:
                res = rebalance_if_due(session_dir)
                if res is None:
                    mark_once(session_dir)
            _update_heartbeat(session_dir)
        except Exception as exc:
            logger.warning("Tick failed for session %s: %s", session_name, exc)
            try:
                _update_heartbeat(session_dir)
            except Exception:
                pass

        time.sleep(poll_interval_sec)


def run_signal_queue_reconciler(poll_interval_sec: int = 10) -> None:
    """Background loop: fill-detect resting LIMIT entries placed via
    signal_queue.py's dispatch_queued_signal, attach protection on first
    confirmed fill (sized to whatever actually filled), and cancel entries
    whose TTL elapsed unfilled.

    This is the ONLY thing that revisits an order after dispatch_queued_signal
    returns -- without it, an entry that doesn't fill within
    BinanceTestnetExecutor._submit_real's ~1-second confirm window is never
    protected and never cancelled. Load-bearing correctness, not optional.
    """
    from src.trading.signal_queue import SignalQueueManager

    logger.info("Signal-queue reconciler started (interval=%ds)", poll_interval_sec)
    mgr = SignalQueueManager()
    while True:
        try:
            result = mgr.reconcile_pending_entries()
            if result.get("processed"):
                logger.info("Signal-queue reconciler processed: %s", result["processed"])
        except Exception:
            logger.exception("Signal-queue reconciler tick failed")
        time.sleep(poll_interval_sec)


def run_sigmalui_ingestion(poll_interval_sec: int = 30) -> None:
    """Continuous background ingestion from SigmaLui Soul Giver feed.
    Validates quality gates, drops stale/unverified/mock signals, and
    enqueues into paper_trading.signal_queue.
    """
    from src.trading.sigmalui_feed_bridge import SigmaluiFeedBridge

    api_url = os.getenv("SIGMALUI_API_URL", "http://host-gateway:3000")
    notional_usd = float(os.getenv("SIGMALUI_AUTO_DISPATCH_NOTIONAL", "25.0"))
    auto_dispatch = os.getenv("SIGMALUI_AUTO_DISPATCH", "false").lower() in ("1", "true", "yes")
    min_score = float(os.getenv("SIGMALUI_MIN_SCORE", "60.0"))
    host_header = os.getenv("SIGMALUI_HOST_HEADER", "")
    node_name = os.getenv("SIGMALUI_NODE_NAME", os.getenv("APP_NAME", "Scaffs_Execution_Node"))
    node_tier = os.getenv("SIGMALUI_NODE_TIER", "PREMIUM_95")

    logger.info(
        "Starting SigmaLui Soul Giver ingestion worker (url=%s, interval=%ds, notional=$%.2f, auto_dispatch=%s)",
        api_url, poll_interval_sec, notional_usd, auto_dispatch,
    )
    bridge = SigmaluiFeedBridge(
        api_url=api_url,
        host_header=host_header,
        node_name=node_name,
        node_tier=node_tier,
    )
    try:
        bridge.register_node()
    except Exception as exc:
        logger.warning("SigmaLui node registration note: %s", exc)

    cycle = 0
    while True:
        cycle += 1
        try:
            res = bridge.sync_and_enqueue_signals(
                auto_dispatch=auto_dispatch,
                notional_usd=notional_usd,
                min_score=min_score,
            )
            examined = res.get("signals_examined", 0)
            enqueued = res.get("enqueued_count", 0)
            dispatched = res.get("dispatched_count", 0)
            if enqueued > 0 or dispatched > 0:
                logger.info("SigmaLui cycle #%d: examined=%d, enqueued=%d, dispatched=%d", cycle, examined, enqueued, dispatched)
            else:
                logger.info("SigmaLui cycle #%d: examined=%d, 0 new (deduped/resting)", cycle, examined)
        except Exception as exc:
            logger.warning("SigmaLui ingestion cycle #%d failed: %s", cycle, exc)

        time.sleep(poll_interval_sec)


def main() -> None:
    initialize_all_sessions()

    # Active sessions: all retained paper workers
    sessions_to_run = [
        ("rebalance_equal_weight_v1", False, 30),
        ("grid_futures_5x_v3", False, 30),
        ("grid_futures_10x_v3", False, 30),
        ("morning_glory_futures", True, 60),
    ]

    threads: list[threading.Thread] = []
    for name, is_funding, interval in sessions_to_run:
        t = threading.Thread(
            target=run_session_worker,
            args=(name, is_funding, interval),
            name=f"Worker-{name}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(0.5)

    reconciler_enabled = os.getenv("SIGNAL_QUEUE_RECONCILER_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if reconciler_enabled:
        reconciler_thread = threading.Thread(
            target=run_signal_queue_reconciler,
            name="Worker-signal-queue-reconciler",
            daemon=True,
        )
        reconciler_thread.start()
        threads.append(reconciler_thread)
    else:
        logger.warning(
            "SIGNAL_QUEUE_RECONCILER_ENABLED=false: resting LIMIT entries will NOT be "
            "fill-detected, protected, or TTL-cancelled after dispatch. Do not disable "
            "this in a live/testnet environment."
        )

    sigmalui_enabled = os.getenv("SIGMALUI_INGESTION_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if sigmalui_enabled:
        sigmalui_interval = int(os.getenv("SIGMALUI_POLL_INTERVAL_SECONDS", "30"))
        sigmalui_thread = threading.Thread(
            target=run_sigmalui_ingestion,
            args=(sigmalui_interval,),
            name="Worker-sigmalui-ingestion",
            daemon=True,
        )
        sigmalui_thread.start()
        threads.append(sigmalui_thread)

    logger.info("All %d paper trading worker services are live and running!", len(threads))

    # Keep main process alive
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Shutting down workers...")


if __name__ == "__main__":
    main()
