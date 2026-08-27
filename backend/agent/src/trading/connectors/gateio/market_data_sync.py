"""Gate.io live USDT perpetual futures market data sync."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from src.market_data.store import MarketDataStore

logger = logging.getLogger(__name__)

HOST = "https://api.gateio.ws"
PREFIX = "/api/v4"


def _get(path: str, timeout: int = 30) -> Any:
    url = f"{HOST}{PREFIX}{path}"
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _symbol(item: dict[str, Any]) -> Optional[str]:
    """Best-effort symbol extraction from a Gate.io futures payload."""
    for key in ("contract", "name"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def sync(store: MarketDataStore) -> dict[str, Any]:
    """Fetch live Gate.io USDT perpetual futures data and store snapshots.

    Returns a summary dict with ``ok`` and per-endpoint counts/errors.
    """
    summary: dict[str, Any] = {
        "ok": False,
        "tickers_count": 0,
        "metadata_count": 0,
        "funding_count": 0,
    }

    try:
        tickers = _get("/futures/usdt/tickers")
        if not isinstance(tickers, list):
            raise TypeError(f"Unexpected tickers response type: {type(tickers)}")

        store.upsert(
            "gateio",
            "tickers",
            "_global",
            {
                "source": f"{HOST}{PREFIX}/futures/usdt/tickers",
                "fetched_at": _now(),
                "data": tickers,
            },
        )
        summary["tickers_count"] = len(tickers)

        # Optional: contract metadata
        try:
            contracts = _get("/futures/usdt/contracts")
            if not isinstance(contracts, list):
                raise TypeError(f"Unexpected contracts response type: {type(contracts)}")

            seen: set[str] = set()
            funding_count = 0
            for contract in contracts:
                if not isinstance(contract, dict):
                    continue
                symbol = _symbol(contract)
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                store.upsert("gateio", "metadata", symbol, contract)

                # Live funding rate is included in the contract snapshot; this
                # avoids 400 errors from /futures/{settle}/funding_rate, which
                # requires a per-contract query parameter.
                if "funding_rate" in contract or "funding_interval" in contract:
                    store.upsert(
                        "gateio",
                        "funding",
                        symbol,
                        {
                            "contract": symbol,
                            "funding_rate": contract.get("funding_rate"),
                            "funding_interval": contract.get("funding_interval"),
                            "funding_next_apply": contract.get("funding_next_apply"),
                            "fetched_at": _now(),
                        },
                    )
                    funding_count += 1
            summary["metadata_count"] = len(seen)
            summary["funding_count"] = funding_count
        except Exception as exc:
            logger.warning("Gate.io contracts sync skipped: %s", exc)
            summary["metadata_error"] = str(exc)

        store.set_status("gateio", "ok")
        summary["ok"] = True
        return summary

    except Exception as exc:
        logger.exception("Gate.io market data sync failed")
        store.set_status("gateio", "failed", str(exc))
        summary["error"] = str(exc)
        return summary
