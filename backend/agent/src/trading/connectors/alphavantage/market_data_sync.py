"""AlphaVantage live market data synchronisation connector."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.market_data.store import MarketDataStore

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.alphavantage.co/query"
_PROVIDER = "alphavantage"
_CRYPTO_SYMBOL = "BTC"
_CRYPTO_MARKET = "USD"
_EQUITY_SYMBOL = "SPY"
_INTERVAL = "5min"


def _load_env_once() -> None:
    """Load backend/agent/.env into the environment if it exists."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_env_once()


def _api_key() -> str:
    return os.getenv("ALPHAVANTAGE_API_KEY", "")


def _count_time_series(payload: dict[str, Any]) -> int:
    """Count bars in an AlphaVantage time-series response."""
    if not isinstance(payload, dict):
        return 0
    for key, value in payload.items():
        if isinstance(key, str) and key.startswith("Time Series") and isinstance(value, dict):
            return len(value)
    return 0


def _has_api_error(payload: dict[str, Any]) -> str | None:
    """Return a message if AlphaVantage rejected the request."""
    if not isinstance(payload, dict):
        return None
    for key in ("Error Message", "Information", "Note"):
        if key in payload:
            return payload[key]
    return None


def _fetch(function: str, symbol: str | None, market: str | None, api_key: str) -> dict[str, Any]:
    params: dict[str, str] = {"function": function, "interval": _INTERVAL, "apikey": api_key}
    if symbol is not None:
        params["symbol"] = symbol
    if market is not None:
        params["market"] = market
    resp = requests.get(_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _store_snapshot(
    store: MarketDataStore,
    function: str,
    symbol: str,
    market: str | None,
    kind: str,
    api_key: str,
) -> dict[str, Any]:
    try:
        payload = _fetch(function, symbol, market, api_key)
    except Exception as exc:
        return {"symbol": symbol, "stored": False, "error": str(exc)}
    error = _has_api_error(payload)
    count = _count_time_series(payload)
    store.upsert(_PROVIDER, kind, symbol, payload)
    result: dict[str, Any] = {"symbol": symbol, "stored": True, "count": count}
    if error:
        result["error"] = error
    return result


def sync(store: MarketDataStore) -> dict[str, Any]:
    """Fetch 5-minute AlphaVantage crypto and equity intraday snapshots.

    Stores the raw JSON payloads in the unified MarketDataStore and records
    provider status. Returns a summary with counts and any errors.
    """
    api_key = _api_key()
    if not api_key:
        error = "ALPHAVANTAGE_API_KEY not configured"
        store.set_status(_PROVIDER, "failed", error)
        return {"provider": _PROVIDER, "status": "failed", "error": error}

    crypto_result = _store_snapshot(
        store, "CRYPTO_INTRADAY", _CRYPTO_SYMBOL, _CRYPTO_MARKET, "crypto_intraday", api_key
    )
    equity_result = _store_snapshot(
        store, "TIME_SERIES_INTRADAY", _EQUITY_SYMBOL, None, "equity_intraday", api_key
    )

    metadata = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "crypto_symbol": _CRYPTO_SYMBOL,
        "equity_symbol": _EQUITY_SYMBOL,
        "interval": _INTERVAL,
        "crypto_count": crypto_result.get("count", 0),
        "equity_count": equity_result.get("count", 0),
        "crypto_error": crypto_result.get("error"),
        "equity_error": equity_result.get("error"),
    }
    store.upsert(_PROVIDER, "metadata", "_global", metadata)

    errors = [
        msg
        for msg in (crypto_result.get("error"), equity_result.get("error"))
        if msg
    ]
    if errors:
        error_str = "; ".join(errors)
        store.set_status(_PROVIDER, "failed", error_str)
        return {
            "provider": _PROVIDER,
            "status": "failed",
            "crypto": crypto_result,
            "equity": equity_result,
            "metadata": metadata,
            "error": error_str,
        }

    store.set_status(_PROVIDER, "ok")
    return {
        "provider": _PROVIDER,
        "status": "ok",
        "crypto": crypto_result,
        "equity": equity_result,
        "metadata": metadata,
    }
