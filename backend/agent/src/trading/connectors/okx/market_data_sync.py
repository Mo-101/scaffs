"""OKX live market data sync connector."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.market_data.store import MarketDataStore

logger = logging.getLogger(__name__)

HOST = "https://www.okx.com"
PREFIX = "/api/v5"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(path: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    url = f"{HOST}{PREFIX}{path}"
    headers = {"Accept": "application/json"}
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise TypeError(f"Unexpected OKX response type: {type(data)}")
    if str(data.get("code")) != "0":
        msg = data.get("msg") or "OKX returned a non-zero code"
        raise RuntimeError(f"OKX API error: {msg}")
    return data


def _symbol(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    inst_id = item.get("instId")
    if inst_id:
        return str(inst_id)
    return None


def sync(store: MarketDataStore) -> dict[str, Any]:
    """Fetch live OKX SWAP market data and store snapshots.

    Returns a summary dict with ``ok`` and per-endpoint counts/errors.
    """
    summary: dict[str, Any] = {
        "ok": False,
        "tickers_count": 0,
        "metadata_count": 0,
        "funding_count": 0,
    }

    try:
        tickers_resp = _get("/market/tickers", params={"instType": "SWAP"})
        tickers = tickers_resp.get("data", [])
        if not isinstance(tickers, list):
            raise TypeError(f"Unexpected tickers response type: {type(tickers)}")

        store.upsert(
            "okx",
            "tickers",
            "_global",
            {
                "source": f"{HOST}{PREFIX}/market/tickers?instType=SWAP",
                "fetched_at": _now(),
                "data": tickers,
            },
        )
        summary["tickers_count"] = len(tickers)

        # Optional: instrument metadata/filters
        try:
            instruments_resp = _get("/public/instruments", params={"instType": "SWAP"})
            instruments = instruments_resp.get("data", [])
            if not isinstance(instruments, list):
                raise TypeError(f"Unexpected instruments response type: {type(instruments)}")

            seen: set[str] = set()
            for item in instruments:
                symbol = _symbol(item)
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                store.upsert("okx", "metadata", symbol, item)
            summary["metadata_count"] = len(seen)
        except Exception as exc:
            logger.warning("OKX instruments sync skipped: %s", exc)
            summary["metadata_error"] = str(exc)

        # Optional: funding rates. instId=ANY returns all available rates in one call.
        try:
            funding_resp = _get("/public/funding-rate", params={"instId": "ANY"})
            funding_rows = funding_resp.get("data", [])
            if not isinstance(funding_rows, list):
                raise TypeError(f"Unexpected funding response type: {type(funding_rows)}")

            seen_funding: set[str] = set()
            for row in funding_rows:
                symbol = _symbol(row)
                if not symbol or symbol in seen_funding:
                    continue
                seen_funding.add(symbol)
                store.upsert(
                    "okx",
                    "funding",
                    symbol,
                    {**row, "fetched_at": _now()},
                )
            summary["funding_count"] = len(seen_funding)
        except Exception as exc:
            logger.warning("OKX funding rates sync skipped: %s", exc)
            summary["funding_error"] = str(exc)

        store.set_status("okx", "ok")
        summary["ok"] = True
        return summary

    except Exception as exc:
        logger.exception("OKX market data sync failed")
        store.set_status("okx", "failed", str(exc))
        summary["error"] = str(exc)
        return summary
