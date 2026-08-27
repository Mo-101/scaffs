"""Idim Ikang Live Feed Bridge for Scaffs.

Continuously ingests upstream signals emitted by Idim Ikang (port 41050 / financial.signals),
routes them through the Signal Priority Queue, validates quality gates, and dispatches
them to the appropriate strategy execution engines (Grid Futures, Time Trading, Morning Glory).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg

from src.trading.signal_queue import SignalQueueManager

logger = logging.getLogger(__name__)

DEFAULT_IDIM_API = os.getenv("IDIM_API_URL", "http://127.0.0.1:41050")
DEFAULT_DSN = os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL") or "dbname=mostar port=5433"


class IdimFeedBridge:
    """Bridges Idim Ikang intelligence stream into Scaffs Priority Queue."""

    def __init__(self, api_url: str = DEFAULT_IDIM_API, dsn: str = DEFAULT_DSN):
        self.api_url = api_url.rstrip("/")
        self.dsn = dsn
        self.queue_mgr = SignalQueueManager(dsn=dsn)
        self._last_processed_signal_id: Optional[str] = None

    def fetch_latest_idim_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch latest emitted signals directly from Idim Ikang API."""
        url = f"{self.api_url}/api/signals"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Scaffs-Bridge/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                signals = data.get("signals", [])
                return signals[:limit]
        except Exception as e:
            logger.warning("Could not reach Idim Ikang API at %s: %s. Falling back to DB query.", url, e)
            return self._fetch_signals_from_db(limit)

    def _fetch_signals_from_db(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fallback to querying financial.signals directly from Postgres."""
        signals = []
        try:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT signal_id, pair, side, score, regime, btc_regime,
                           entry, stop_loss, take_profit, signal_family, reason_trace, ts
                    FROM financial.signals
                    ORDER BY ts DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                for r in cur.fetchall():
                    signals.append({
                        "signal_id": str(r[0]),
                        "pair": r[1],
                        "side": r[2],
                        "score": float(r[3]) if r[3] is not None else 65.0,
                        "regime": r[4],
                        "btc_regime": r[5],
                        "entry": float(r[6]) if r[6] is not None else None,
                        "stop_loss": float(r[7]) if r[7] is not None else None,
                        "take_profit": float(r[8]) if r[8] is not None else None,
                        "signal_family": r[9],
                        "reason_trace": r[10] if isinstance(r[10], dict) else json.loads(r[10] or "{}"),
                        "ts": r[11].isoformat() if r[11] else None,
                    })
        except Exception as exc:
            logger.error("DB query to financial.signals failed: %s", exc)
        return signals

    def sync_and_enqueue_signals(self, auto_dispatch: bool = False, notional_usd: float = 25.0) -> Dict[str, Any]:
        """Ingest new signals from Idim Ikang, pass through gates, route, and optionally dispatch."""
        signals = self.fetch_latest_idim_signals(limit=20)
        enqueued = []
        rejected = []
        dispatched = []

        # Use a single database connection for the whole batch; opening 20
        # separate psycopg connections is the main cause of Idim sync stalls.
        try:
            with psycopg.connect(self.dsn) as conn:
                # Check active queue records to avoid re-enqueuing a signal that is still
                # pending, dispatched or being processed. Expired/rejected/completed
                # entries may be re-ingested so the feed stays visible on refresh.
                existing_signal_ids = set()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT source_signal_id
                            FROM paper_trading.signal_queue
                            WHERE source_signal_id IS NOT NULL
                              AND status NOT IN ('EXPIRED','REJECTED','COMPLETED','CANCELLED','EXECUTION_FAILED','COLLISION_BLOCKED');
                            """
                        )
                        for r in cur.fetchall():
                            existing_signal_ids.add(r[0])
                except Exception as e:
                    logger.warning("Could not query existing signal_ids: %s", e)

                for sig in signals:
                    sig_id = str(sig.get("signal_id") or "")
                    if not sig_id or sig_id in existing_signal_ids:
                        continue

                    symbol = sig.get("pair") or sig.get("symbol")
                    side = sig.get("side")
                    score = float(sig.get("score") or sig.get("setup_score") or 65.0)
                    timeframe = "15m" if "15m" in str(sig.get("signal_family", "")).lower() else "5m"

                    crit = {
                        "regime": sig.get("regime"),
                        "btc_regime": sig.get("btc_regime"),
                        "signal_family": sig.get("signal_family"),
                        "entry": sig.get("entry"),
                        "stop_loss": sig.get("stop_loss"),
                        "take_profit": sig.get("take_profit"),
                        "reason_trace": sig.get("reason_trace"),
                    }

                    res = self.queue_mgr.enqueue_signal(
                        symbol=symbol,
                        side=side,
                        producer="idim_ikang",
                        timeframe=timeframe,
                        raw_score=score,
                        source_signal_id=sig_id,
                        criteria_vector=crit,
                        ttl_seconds=600,
                        conn=conn,
                    )

                    if res.get("ok"):
                        enqueued.append(res)
                        existing_signal_ids.add(sig_id)

                        if auto_dispatch:
                            try:
                                dispatch_res = self.queue_mgr.dispatch_queued_signal(
                                    queue_id=res["id"],
                                    notional_usd=notional_usd,
                                )
                                dispatched.append(dispatch_res)
                            except Exception as e:
                                logger.error("Failed to auto-dispatch signal %s: %s", res["id"], e)
                    else:
                        rejected.append({"symbol": symbol, "side": side, "score": score, "reason": res.get("reason")})
        except Exception as exc:
            logger.error("Idim sync batch failed: %s", exc)

        return {
            "ok": True,
            "signals_examined": len(signals),
            "enqueued_count": len(enqueued),
            "rejected_count": len(rejected),
            "dispatched_count": len(dispatched),
            "enqueued": enqueued,
            "rejected": rejected,
            "dispatched": dispatched,
        }
