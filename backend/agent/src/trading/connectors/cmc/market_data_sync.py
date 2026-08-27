"""CoinMarketCap live market data synchronisation.

Fetches top-100 listings and selected symbol quotes from the CoinMarketCap
Pro API and persists them in the unified MarketDataStore.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

from src.market_data import MarketDataStore

logger = logging.getLogger(__name__)

_BASE_URL = "https://pro-api.coinmarketcap.com"
_LISTINGS_ENDPOINT = f"{_BASE_URL}/v1/cryptocurrency/listings/latest"
_QUOTES_ENDPOINT = f"{_BASE_URL}/v2/cryptocurrency/quotes/latest"
_WATCHLIST = ["BTC", "ETH", "BNB"]


def _headers() -> dict[str, str]:
    key = os.getenv("CMC_API_KEY")
    if not key:
        raise RuntimeError("CMC_API_KEY is not set")
    return {
        "X-CMC_PRO_API_KEY": key,
        "Accept": "application/json",
    }


def sync(store: MarketDataStore) -> dict[str, Any]:
    """Fetch CMC live market data and persist it as read-only snapshots.

    Returns a summary with the number of listings and per-symbol quotes stored.
    """
    result: dict[str, Any] = {
        "listings_count": 0,
        "quotes_count": 0,
        "symbols": [],
    }

    try:
        # 1. Top-100 latest listings
        listings_resp = requests.get(
            _LISTINGS_ENDPOINT,
            headers=_headers(),
            params={"limit": 100, "convert": "USD"},
            timeout=30,
        )
        listings_resp.raise_for_status()
        listings = listings_resp.json()

        data = listings.get("data")
        if not isinstance(data, list):
            raise ValueError("CMC listings response missing 'data' list")

        result["listings_count"] = len(data)
        store.upsert("cmc", "listings", "_global", listings)

        # 2. Specific symbol quotes
        quotes_resp = requests.get(
            _QUOTES_ENDPOINT,
            headers=_headers(),
            params={"symbol": ",".join(_WATCHLIST), "convert": "USD"},
            timeout=30,
        )
        quotes_resp.raise_for_status()
        quotes = quotes_resp.json()

        quote_data = quotes.get("data", {})
        if isinstance(quote_data, dict):
            for symbol, symbol_payload in quote_data.items():
                store.upsert(
                    "cmc",
                    "quote",
                    symbol,
                    {"status": quotes.get("status"), "data": {symbol: symbol_payload}},
                )
                result["symbols"].append(symbol)
                result["quotes_count"] += 1

        store.set_status("cmc", "ok")
    except Exception as exc:
        logger.exception("CMC market data sync failed")
        store.set_status("cmc", "failed", str(exc))
        result["error"] = str(exc)

    return result
