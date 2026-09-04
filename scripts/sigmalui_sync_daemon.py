#!/usr/bin/env python3
"""SigmaLui Soul Giver Continuous Ingestion & Auto-Dispatch Daemon.

Polls SigmaLui Soul Giver signal endpoint every 30s, ingests signals into
Scaffs priority queue, enforces risk gates, and auto-dispatches to Binance
Testnet when configured.
"""

import os
import sys
import time
import signal as os_signal
import logging
from pathlib import Path

# Ensure backend/agent is in sys.path regardless of where the script is located
current_file = Path(__file__).resolve()
ROOT = current_file.parent.parent
for candidate in [
    Path("/app/backend/agent"),
    ROOT,
    ROOT / "backend" / "agent",
]:
    if candidate.exists() and (candidate / "src").exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# Load .env so local runs pick up SIGMALUI_API_URL, host header, and DB settings.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

# If in container, default to container network
if os.path.exists("/.dockerenv") or os.getenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK"):
    os.environ.setdefault("DATABASE_URL", "postgresql://postgres:mostar@postgres:5432/mostar")
    os.environ.setdefault("VIBE_PAPER_DATABASE_URL", "postgresql://postgres:mostar@postgres:5432/mostar")
    os.environ.setdefault("SIGMALUI_API_URL", "http://host-gateway:3000")
else:
    os.environ["POSTGRES_HOST_PORT"] = os.getenv("POSTGRES_HOST_PORT", "5434")

from src.trading.sigmalui_feed_bridge import SigmaluiFeedBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sigmalui_daemon")

PID_FILE = Path("/tmp/sigmalui_sync_daemon.pid")


def acquire_pid_lock():
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # Check if process is still running
            os.kill(old_pid, 0)
            logger.error("Another SigmaLui daemon is already active (PID %d). Refusing to start duplicate.", old_pid)
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Process is stale, take over lock
            pass
        except PermissionError:
            logger.error("Existing SigmaLui daemon PID file exists and is owned by another process.")
            sys.exit(1)
    PID_FILE.write_text(str(os.getpid()))


def release_pid_lock():
    if PID_FILE.exists():
        try:
            if int(PID_FILE.read_text().strip()) == os.getpid():
                PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass


running = True


def handle_signal(sig, frame):
    global running
    logger.info("Received termination signal %s. Shutting down daemon...", sig)
    running = False
    release_pid_lock()


os_signal.signal(os_signal.SIGINT, handle_signal)
os_signal.signal(os_signal.SIGTERM, handle_signal)


def main():
    acquire_pid_lock()
    try:
        poll_interval = int(os.getenv("SIGMALUI_POLL_INTERVAL_SECONDS", "30"))
        notional_usd = float(os.getenv("SIGMALUI_AUTO_DISPATCH_NOTIONAL", "25.0"))
        auto_dispatch = os.getenv("SIGMALUI_AUTO_DISPATCH", "false").lower() in ("1", "true", "yes")
        min_score = float(os.getenv("SIGMALUI_MIN_SCORE", "60.0"))
        host_header = os.getenv("SIGMALUI_HOST_HEADER", "")
        node_name = os.getenv("SIGMALUI_NODE_NAME", os.getenv("APP_NAME", "Scaffs_Execution_Node"))
        node_tier = os.getenv("SIGMALUI_NODE_TIER", "PREMIUM_95")

        logger.info(
            "Starting SigmaLui Soul Giver Ingestion Daemon (interval=%ds, notional=$%.2f, auto_dispatch=%s, min_score=%.1f, node=%s)...",
            poll_interval, notional_usd, auto_dispatch, min_score, node_name,
        )
        bridge = SigmaluiFeedBridge(host_header=host_header, node_name=node_name, node_tier=node_tier)
        bridge.register_node()

        cycle = 0
        while running:
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
                    logger.info("Cycle #%d: examined=%d, enqueued=%d, dispatched=%d", cycle, examined, enqueued, dispatched)
                else:
                    logger.debug("Cycle #%d: examined=%d, no new signals", cycle, examined)
            except Exception as e:
                logger.error("Error in sync cycle #%d: %s", cycle, e, exc_info=True)

            for _ in range(poll_interval):
                if not running:
                    break
                time.sleep(1)

        logger.info("SigmaLui Ingestion Daemon stopped cleanly.")
    finally:
        release_pid_lock()


if __name__ == "__main__":
    main()
