#!/usr/bin/env python3
"""Idim Ikang Continuous Ingestion & Auto-Dispatch Daemon.

Polls Idim Ikang intelligence stream every 30s, ingests signals into Scaffs
priority queue, enforces risk gates, and auto-dispatches to Binance Testnet.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "backend" / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

# Ensure correct DSN resolution for local Docker Postgres
os.environ["POSTGRES_HOST_PORT"] = os.getenv("POSTGRES_HOST_PORT", "5434")

from src.trading.idim_feed_bridge import IdimFeedBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("idim_daemon")

running = True

def handle_signal(sig, frame):
    global running
    logger.info("Received termination signal %s. Shutting down daemon...", sig)
    running = False

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def main():
    poll_interval = int(os.getenv("IDIM_POLL_INTERVAL_SECONDS", "30"))
    notional_usd = float(os.getenv("IDIM_AUTO_DISPATCH_NOTIONAL", "25.0"))
    # Auto-dispatch is opt-IN. It was hardcoded True, so the daemon fired every
    # signal it ingested regardless of configuration -- there was no way to run
    # ingest-only and pick entries by hand. Default False so an unset env means
    # "queue it, a human decides", which is the safe direction; SigmaLui's bridge
    # already defaults auto_dispatch=False for the same reason.
    from src.trading.runtime_settings import auto_dispatch_enabled
    auto_dispatch = auto_dispatch_enabled("IDIM_AUTO_DISPATCH")
    
    logger.info(
        "Starting Idim Ikang Ingestion Daemon (interval=%ds, notional=$%.2f, auto_dispatch=%s)...",
        poll_interval, notional_usd, auto_dispatch,
    )
    bridge = IdimFeedBridge()
    
    cycle = 0
    while running:
        cycle += 1
        try:
            # Re-read per cycle so the dashboard toggle reaches this daemon too.
            cycle_auto = auto_dispatch_enabled("IDIM_AUTO_DISPATCH")
            if cycle_auto != auto_dispatch:
                logger.info("Idim auto_dispatch changed %s -> %s", auto_dispatch, cycle_auto)
                auto_dispatch = cycle_auto
            res = bridge.sync_and_enqueue_signals(auto_dispatch=cycle_auto, notional_usd=notional_usd)
            examined = res.get("signals_examined", 0)
            enqueued = res.get("enqueued_count", 0)
            dispatched = res.get("dispatched_count", 0)
            
            if enqueued > 0 or dispatched > 0:
                logger.info("Cycle #%d: examined=%d, enqueued=%d, dispatched=%d", cycle, examined, enqueued, dispatched)
            else:
                logger.debug("Cycle #%d: examined=%d, no new signals", cycle, examined)
        except Exception as e:
            logger.error("Error in sync cycle #%d: %s", cycle, e, exc_info=True)
            
        for _ in range(poll_interval):
            if not running:
                break
            time.sleep(1)

    logger.info("Idim Ingestion Daemon stopped cleanly.")

if __name__ == "__main__":
    main()
