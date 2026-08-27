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

    logger.info("All %d paper trading worker services are live and running!", len(threads))

    # Keep main process alive
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Shutting down workers...")


if __name__ == "__main__":
    main()
