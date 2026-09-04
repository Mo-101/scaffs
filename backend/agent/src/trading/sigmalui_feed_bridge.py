"""SigmaLui Soul Giver Live Feed Bridge for Scaffs.

Polls the SigmaLui /api/soul/signals endpoint, ingests high-conviction
directional directives into the Scaffs Signal Priority Queue, validates
quality gates, and optionally dispatches them to the configured strategy.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg

from src.trading.signal_queue import SignalQueueManager

logger = logging.getLogger(__name__)


def _get_default_dsn() -> str:
    from src.db_dsn import resolve_dsn

    return resolve_dsn()


DEFAULT_SIGMALUI_API_URL = os.environ.get("SIGMALUI_API_URL", "https://sigma.mostarindustries.com")
DEFAULT_SIGMALUI_API_KEY = os.environ.get("SIGMALUI_API_KEY", os.environ.get("SOUL_API_KEY", ""))
DEFAULT_SIGMALUI_HMAC_SECRET = os.environ.get("SIGMALUI_HMAC_SECRET", os.environ.get("SOUL_HMAC_SECRET", ""))
DEFAULT_SIGMALUI_HOST_HEADER = os.environ.get("SIGMALUI_HOST_HEADER", "")
DEFAULT_SIGMALUI_NODE_NAME = os.environ.get("SIGMALUI_NODE_NAME", os.environ.get("APP_NAME", "Scaffs_Execution_Node"))
DEFAULT_SIGMALUI_NODE_TIER = os.environ.get("SIGMALUI_NODE_TIER", "PREMIUM_95")


class SigmaluiFeedBridge:
    """Bridges SigmaLui Soul Giver signals into the Scaffs Priority Queue."""

    def __init__(
        self,
        api_url: str = DEFAULT_SIGMALUI_API_URL,
        api_key: str = DEFAULT_SIGMALUI_API_KEY,
        hmac_secret: str = DEFAULT_SIGMALUI_HMAC_SECRET,
        host_header: str = DEFAULT_SIGMALUI_HOST_HEADER,
        node_name: str = DEFAULT_SIGMALUI_NODE_NAME,
        node_tier: str = DEFAULT_SIGMALUI_NODE_TIER,
        dsn: Optional[str] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.hmac_secret = hmac_secret
        self.host_header = host_header.strip()
        self.node_name = node_name
        self.node_tier = node_tier
        self.dsn = dsn or _get_default_dsn()
        self.queue_mgr = SignalQueueManager(dsn=self.dsn)
        self._last_processed_signal_id: Optional[str] = None
        self._node_registered = False

    def _request_headers(self, json_body: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "User-Agent": f"Scaffs-SigmaLui-Bridge/1.0 ({self.node_name})",
            "Accept": "application/json",
        }
        if self.host_header:
            headers["Host"] = self.host_header
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _post_json(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.api_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        headers = self._request_headers(json_body=True)
        headers["Content-Length"] = str(len(data))
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def register_node(self) -> Optional[Dict[str, Any]]:
        """Register this Scaffs node in the SigmaLui performance mesh."""
        if self._node_registered:
            return None
        try:
            result = self._post_json(
                "/api/soul/generate-key",
                {"node_name": self.node_name, "tier": self.node_tier},
            )
            self._node_registered = True
            logger.info("SigmaLui node registered: %s", result.get("message", "ok"))
            return result
        except urllib.error.HTTPError as e:
            logger.warning("SigmaLui node registration returned %s: %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.warning("SigmaLui node registration failed: %s", e)
            return None

    def share_outcome(self, outcome: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Share a trade execution outcome back to SigmaLui for reputation scoring."""
        payload = {
            "nodeId": outcome.get("node_id", self.node_name),
            "nodeIdentity": self.node_name,
            "signalId": outcome.get("signal_id", ""),
            "asset": outcome.get("asset", ""),
            "futuresPair": outcome.get("futures_pair", ""),
            "direction": outcome.get("direction", ""),
            "entryPrice": outcome.get("entry_price", 0.0),
            "exitPrice": outcome.get("exit_price", 0.0),
            "pnlPct": outcome.get("pnl_pct", 0.0),
            "slippage": outcome.get("slippage", 0.0),
            "entry_lag": outcome.get("entry_lag", 0.0),
            "wasProfitable": outcome.get("was_profitable", outcome.get("pnl_pct", 0.0) > 0),
        }
        try:
            return self._post_json("/api/soul/share-outcome", payload)
        except Exception as e:
            logger.warning("SigmaLui outcome share failed: %s", e)
            return None

    def fetch_latest_sigmalui_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch latest emitted signals from the SigmaLui Soul API."""
        for endpoint in ("/api/soul/signals", "/api/soul/suck-signals"):
            url = f"{self.api_url}{endpoint}"
            try:
                req = urllib.request.Request(url, headers=self._request_headers())
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    signals = data.get("signals", [])
                    return signals[:limit]
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    logger.debug("SigmaLui endpoint not found: %s", url)
                    continue
                logger.warning("SigmaLui API returned %s for %s: %s", e.code, url, e.reason)
                return []
            except urllib.error.URLError as e:
                logger.warning("Could not reach SigmaLui API at %s: %s", url, e.reason)
                return []
            except Exception as e:
                logger.warning("SigmaLui fetch error at %s: %s", url, e)
                return []
        logger.warning("No SigmaLui signal endpoint found at %s", self.api_url)
        return []

    def _normalize_symbol(self, raw: Optional[str]) -> str:
        """Normalize a SigmaLui futures pair to a Binance-compatible symbol."""
        if not raw:
            return ""
        sym = str(raw).upper().replace("-", "").replace("/", "").replace(".", "")
        # Strip common perpetual suffixes that do not belong in Binance symbols.
        for suffix in ("P", "PERP"):
            if sym.endswith(suffix):
                sym = sym[: -len(suffix)]
        return sym

    def _normalize_side(self, raw: Optional[str]) -> str:
        side = str(raw or "").upper()
        if side in ("STRONG_BUY", "BUY", "LONG"):
            return "BUY"
        if side in ("STRONG_SELL", "SELL", "SHORT"):
            return "SELL"
        return side

    def _parse_timestamp(self, raw: Any) -> Optional[datetime]:
        if not raw:
            return None
        try:
            if isinstance(raw, (int, float)):
                ts = raw / 1000.0 if raw > 1e11 else float(raw)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            if isinstance(raw, str):
                text = raw.strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                try:
                    return datetime.fromisoformat(text)
                except ValueError:
                    # SigmaLui sometimes emits bare time strings (e.g. "14:22:10").
                    # Without a date/timezone we cannot know the real age, so treat
                    # the signal as fresh at the moment of ingestion to avoid
                    # penalising it with a multi-hour staleness penalty.
                    for fmt in ("%H:%M:%S", "%H:%M"):
                        try:
                            datetime.strptime(text, fmt)
                            return datetime.now(timezone.utc)
                        except ValueError:
                            continue
                    raise
        except Exception as e:
            logger.warning("Could not parse SigmaLui timestamp %r: %s", raw, e)
        return None

    def _extract_signal_id(self, sig: Dict[str, Any]) -> str:
        return str(sig.get("id") or sig.get("signal_id") or sig.get("soulDirective") or f"sigmalui-{datetime.now(timezone.utc).isoformat()}")

    def sync_and_enqueue_signals(
        self,
        auto_dispatch: bool = False,
        notional_usd: float = 25.0,
        min_score: float = 60.0,
    ) -> Dict[str, Any]:
        """Ingest new SigmaLui signals, pass through gates, and optionally dispatch."""
        self.register_node()
        signals = self.fetch_latest_sigmalui_signals(limit=20)
        enqueued = []
        rejected = []
        dispatched = []

        try:
            with psycopg.connect(self.dsn) as conn:
                existing_signal_ids = set()
                try:
                    with conn.cursor() as cur:
                        # This NOT IN list is the re-enqueue-eligible set: a
                        # signal_id in any status listed here may be ingested
                        # again on a later poll, because that outcome says
                        # nothing about whether the setup is still valid.
                        # Anything NOT listed (including PROTECTED and the
                        # ENTRY_TOO_FAR_FROM_MARK /
                        # PROTECTION_ABANDONED_NO_POSITION rejections written
                        # by signal_queue) is deliberately absent so the same
                        # source_signal_id is not re-ingested. Upstream feeds
                        # re-emit a setup under a stable id indefinitely, so
                        # adding a stale-signal rejection here would restart
                        # the enqueue -> dead LIMIT -> TTL-cancel -> re-enqueue
                        # churn those statuses exist to stop.
                        cur.execute(
                            """
                            SELECT source_signal_id
                            FROM paper_trading.signal_queue
                            WHERE producer = 'sigmalui' AND source_signal_id IS NOT NULL;
                            """
                        )
                        for r in cur.fetchall():
                            existing_signal_ids.add(r[0])
                except Exception as e:
                    logger.warning("Could not query existing signal_ids: %s", e)

                for sig in signals:
                    sig_id = self._extract_signal_id(sig)
                    if not sig_id or sig_id in existing_signal_ids:
                        continue

                    symbol = self._normalize_symbol(
                        sig.get("futuresPair") or sig.get("asset") or sig.get("symbol")
                    )
                    if not symbol:
                        rejected.append({"signal": sig_id, "reason": "missing symbol"})
                        continue

                    side = self._normalize_side(sig.get("action") or sig.get("side"))
                    if side not in ("BUY", "SELL"):
                        rejected.append({"signal": sig_id, "reason": f"unrecognized side {side!r}"})
                        continue

                    raw_score = sig.get("topsisScore") or sig.get("confidencePct")
                    if raw_score is None:
                        raw_score = 0.0
                    try:
                        score = float(raw_score)
                    except (TypeError, ValueError):
                        score = 0.0
                    # topsisScore is a 0-1 coefficient; scale to 0-100 for Scaffs gates.
                    if score <= 1.0 and ("topsisScore" in sig or "topsis_score" in sig):
                        score = score * 100.0

                    if score < min_score:
                        rejected.append({"signal": sig_id, "reason": f"score {score:.2f} below min {min_score}"})
                        continue

                    entry_px = sig.get("entryPrice") or sig.get("entry") or sig.get("price")
                    sl_val = sig.get("stopLoss") or sig.get("stop_loss") or sig.get("sl")
                    tp_val = sig.get("takeProfit1") or sig.get("take_profit") or sig.get("tp") or sig.get("target1")
                    timeframe = sig.get("timeframe") or "15m"

                    # Enforce price geometry if all three are present.
                    if entry_px is not None and sl_val is not None and tp_val is not None:
                        try:
                            entry = float(entry_px)
                            sl = float(sl_val)
                            tp = float(tp_val)
                            if side == "BUY" and not (tp > entry > sl):
                                rejected.append({"signal": sig_id, "reason": "invalid LONG geometry"})
                                continue
                            if side == "SELL" and not (sl > entry > tp):
                                rejected.append({"signal": sig_id, "reason": "invalid SHORT geometry"})
                                continue
                        except (TypeError, ValueError):
                            pass

                    signal_generated_dt = self._parse_timestamp(
                        sig.get("timestamp") or sig.get("ts") or sig.get("createdAt") or sig.get("created_at")
                    )

                    now_utc = datetime.now(timezone.utc)
                    age_sec = (now_utc - (signal_generated_dt or now_utc)).total_seconds()
                    # Stale Gate: signals older than 600s TTL enter as EXPIRED/BACKFILL, never PENDING
                    is_stale = age_sec > 600.0

                    crit = {
                        "regime": sig.get("marketRegime") or sig.get("regime"),
                        "signal_family": "sigmalui",
                        "entry": entry_px,
                        "stop_loss": sl_val,
                        "take_profit": tp_val,
                        "topsis_score": sig.get("topsisScore"),
                        "confluence_reason": sig.get("confluenceReason") or sig.get("explanation"),
                        "soul_directive": sig.get("soulDirective"),
                        "ingestion_mode": "BACKFILL" if is_stale else "LIVE",
                        "backfilled": is_stale,
                    }

                    initial_status = "EXPIRED" if is_stale else "PENDING"
                    rejection_reason = f"stale-entry: signal age {age_sec:.1f}s exceeds 600s TTL" if is_stale else None

                    res = self.queue_mgr.enqueue_signal(
                        symbol=symbol,
                        side=side,
                        producer="sigmalui",
                        timeframe=timeframe,
                        raw_score=score,
                        source_signal_id=sig_id,
                        criteria_vector=crit,
                        signal_timestamp=signal_generated_dt.isoformat() if signal_generated_dt else None,
                        ttl_seconds=600,
                        initial_status=initial_status,
                        rejection_reason=rejection_reason,
                        conn=conn,
                    )

                    if res.get("ok"):
                        enqueued.append(res)
                        existing_signal_ids.add(sig_id)

                        # Only auto-dispatch live, fresh PENDING signals
                        if auto_dispatch and initial_status == "PENDING" and not res.get("duplicate"):
                            try:
                                dispatch_res = self.queue_mgr.dispatch_queued_signal(
                                    queue_id=res["id"],
                                    notional_usd=notional_usd,
                                )
                                dispatched.append(dispatch_res)
                            except Exception as e:
                                logger.error("Failed to auto-dispatch SigmaLui signal %s: %s", res["id"], e)
                    else:
                        rejected.append({
                            "signal": sig_id,
                            "symbol": symbol,
                            "side": side,
                            "score": score,
                            "reason": res.get("reason"),
                        })
        except Exception as exc:
            logger.error("SigmaLui sync batch failed: %s", exc, exc_info=True)

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
