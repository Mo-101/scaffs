"""Persistent cache for Binance USD-M Futures Testnet market metadata.

The ``sync()`` method fetches live public exchange data on demand; every other
method is read-only from the cached JSON files.  This keeps the repository
clean and allows a daily cron/frontend job to refresh data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .futures_sdk import (
    BinanceAPIError,
    BinanceFuturesClient,
    BinanceFuturesConfig,
    _format_symbol,
)

logger = logging.getLogger(__name__)


def _default_store_dir() -> Path:
    """Locate ``paper_sessions/market_data`` from this module's position."""
    return Path(__file__).resolve().parents[4] / "paper_sessions" / "market_data"


class MarketDataStore:
    """Local JSON cache for Binance Futures Testnet market metadata."""

    def __init__(self, store_dir: Optional[Path] = None):
        self.store_dir = store_dir or _default_store_dir()
        self.market_data_path = self.store_dir / "market_data.json"
        self.symbols_path = self.store_dir / "symbols.json"
        # Prefer env credentials so leverage-bracket data is available; fall back
        # to a key-less testnet config for public exchangeInfo/fundingRate calls.
        try:
            self._client = BinanceFuturesClient(BinanceFuturesConfig.from_env())
        except RuntimeError:
            self._client = BinanceFuturesClient(BinanceFuturesConfig())

    def sync(self) -> dict[str, Any]:
        """Fetch live market metadata and persist it locally.

        Returns a summary dict with ``ok``, ``saved_at`` (UTC ISO), and
        ``symbol_count``.
        """
        self.store_dir.mkdir(parents=True, exist_ok=True)

        exchange_info = self._client.get_exchange_info()
        funding_rates = self._client.get_funding_rate()
        try:
            leverage_brackets = self._client.get_leverage_brackets()
        except BinanceAPIError as exc:
            logger.warning(
                "get_leverage_brackets failed (requires a valid testnet API key): %s",
                exc,
            )
            leverage_brackets = []
        saved_at = datetime.now(timezone.utc).isoformat()

        symbols = self._build_symbols(exchange_info)
        market_data = {
            "saved_at": saved_at,
            "exchange_info": exchange_info,
            "leverage_brackets": leverage_brackets,
            "funding_rates": funding_rates,
        }

        self.market_data_path.write_text(
            json.dumps(market_data, indent=2), encoding="utf-8"
        )
        self.symbols_path.write_text(
            json.dumps(symbols, indent=2), encoding="utf-8"
        )

        logger.info(
            "binance_testnet market data synced: %s, symbols=%d",
            self.store_dir,
            len(symbols),
        )
        return {
            "ok": True,
            "saved_at": saved_at,
            "symbol_count": len(symbols),
        }

    def _build_symbols(self, exchange_info: dict[str, Any]) -> list[dict[str, Any]]:
        """Build the lightweight ``symbols.json`` from exchangeInfo."""
        result: list[dict[str, Any]] = []
        for s in exchange_info.get("symbols", []):
            if s.get("status") != "TRADING":
                continue
            if s.get("contractType") != "PERPETUAL":
                continue
            if s.get("quoteAsset") != "USDT":
                continue

            filters = {
                f.get("filterType", ""): f
                for f in s.get("filters", [])
                if isinstance(f, dict)
            }
            price_filter = filters.get("PRICE_FILTER") or {}
            lot_filter = (
                filters.get("LOT_SIZE")
                or filters.get("MARKET_LOT_SIZE")
                or {}
            )
            min_notional_filter = filters.get("MIN_NOTIONAL") or {}
            notional_filter = filters.get("NOTIONAL") or {}

            result.append(
                {
                    "symbol": s.get("symbol"),
                    "baseAsset": s.get("baseAsset"),
                    "quoteAsset": s.get("quoteAsset"),
                    "contractType": s.get("contractType"),
                    "status": s.get("status"),
                    "tickSize": price_filter.get("tickSize"),
                    "stepSize": lot_filter.get("stepSize"),
                    "minNotional": (
                        min_notional_filter.get("notional")
                        or notional_filter.get("minNotional")
                    ),
                    "filters": filters,
                }
            )
        return result

    def _load_market_data(self) -> dict[str, Any]:
        if not self.market_data_path.exists():
            raise FileNotFoundError(
                f"Market data not synced: {self.market_data_path}"
            )
        return json.loads(self.market_data_path.read_text(encoding="utf-8"))

    def _load_symbols(self) -> list[dict[str, Any]]:
        if not self.symbols_path.exists():
            raise FileNotFoundError(
                f"Market data not synced: {self.symbols_path}"
            )
        return json.loads(self.symbols_path.read_text(encoding="utf-8"))

    def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Return the stored filters / tick / step / min notional for ``symbol``."""
        target = _format_symbol(symbol)
        for s in self._load_symbols():
            if s.get("symbol", "") == target:
                return s
        return None

    def get_leverage_bracket(self, symbol: str) -> dict[str, Any] | None:
        """Return the stored leverage-bracket group for ``symbol``."""
        target = _format_symbol(symbol)
        for bracket in self._load_market_data().get("leverage_brackets", []):
            if bracket.get("symbol", "") == target:
                return bracket
        return None

    def get_funding_rate(self, symbol: str) -> dict[str, Any] | None:
        """Return the stored funding rate for ``symbol`` (latest by fundingTime)."""
        target = _format_symbol(symbol)
        rates = [
            fr
            for fr in self._load_market_data().get("funding_rates", [])
            if fr.get("symbol", "") == target
        ]
        if not rates:
            return None
        latest = max(rates, key=lambda r: r.get("fundingTime", 0))
        return latest
