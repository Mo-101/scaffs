"""Bybit live market data sync connector.

Fetches public V5 market snapshots and writes them to the unified
``MarketDataStore``.  This connector is read-only and never places orders.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.market_data.store import MarketDataStore

logger = logging.getLogger(__name__)

_MAINNET = "https://api.bybit.com"
_TESTNET = "https://api-testnet.bybit.com"


def _base_url() -> str:
    """Return the Bybit API base URL, preferring testnet when configured."""
    base = os.getenv("BYBIT_BASE_URL") or ""
    key = os.getenv("BYBIT_API_KEY") or ""
    secret = os.getenv("BYBIT_API_SECRET") or ""
    env = f"{base} {key} {secret}".lower()
    if "testnet" in env:
        return _TESTNET
    return base.rstrip("/") if base else _MAINNET


def _get(path: str, params: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    """Public GET a Bybit V5 endpoint and validate the response."""
    url = _base_url() + path
    logger.debug("Bybit GET %s with params %s", url, params)
    resp = requests.get(url, params=params, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"Bybit HTTP {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    if body.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error {body.get('retCode')}: {body.get('retMsg')}")
    return body


def _is_usdt_perp(ticker: dict[str, Any]) -> bool:
    sym = ticker.get("symbol", "")
    return sym.endswith("USDT") and ticker.get("fundingRate") is not None


def sync(store: MarketDataStore) -> dict[str, Any]:
    """Fetch Bybit linear USDT perpetual market data and persist it.

    Returns a summary with the number of symbols synced and the number of
    funding rows stored.
    """
    try:
        tickers_body = _get("/v5/market/tickers", {"category": "linear"})
        tickers = tickers_body.get("result", {}).get("list", [])
        perps = [t for t in tickers if _is_usdt_perp(t)]
        symbols = [t["symbol"] for t in perps]

        store.upsert("bybit", "tickers", "_global", {"category": "linear", "list": perps})

        for t in perps:
            store.upsert(
                "bybit",
                "funding",
                t["symbol"],
                {
                    "symbol": t["symbol"],
                    "fundingRate": t.get("fundingRate"),
                    "nextFundingTime": t.get("nextFundingTime"),
                },
            )

        symbol_set = set(symbols)
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"category": "linear", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            info_body = _get("/v5/market/instruments-info", params)
            info_result = info_body.get("result", {})
            for inst in info_result.get("list", []):
                sym = inst.get("symbol")
                if sym in symbol_set:
                    store.upsert("bybit", "metadata", sym, inst)
            cursor = info_result.get("nextPageCursor")
            if not cursor:
                break

        store.set_status("bybit", "ok")
        logger.info("bybit synced %s USDT perpetual symbols", len(symbols))
        return {"symbols": len(symbols), "funding_rows": len(symbols)}
    except Exception as exc:
        store.set_status("bybit", "failed", str(exc))
        logger.warning("bybit sync failed: %s", exc)
        raise
