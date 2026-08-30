"""Exchange-metadata allowlist for tradeable symbols.

A symbol must be validated against Binance's own ``/fapi/v1/exchangeInfo``,
never against a character-class regex. Binance USD-M Futures has listed
Chinese-character perpetuals since October 2025 -- at the time of writing it
lists five (``龙虾USDT``, ``币安人生USDT``, ``我踏马来了USDT``, ``测试测试USDT``,
``牛来USDT``) -- so "non-ASCII" says nothing about whether a market is real.

What actually blocked those signals was ``status``: both ``龙虾USDT`` and the
ASCII ``ZKCUSDT`` were ``PENDING_TRADING``. ``set_margin_type`` fails on a
market that is listed but not yet open, and the failure surfaced as a
misleading ``MARGIN_MODE_MISMATCH`` after the dispatcher had already done
collision, sizing and leverage work. Of 734 listed markets 61 are
``PENDING_TRADING`` and 61 ``SETTLING``, so this recurs constantly.

Checking status up front turns that into an honest, cheap, terminal answer.
These blocks are deliberately absent from the retry-eligible status list in
``idim_feed_bridge.sync_and_enqueue_signals``: a symbol that is not listed, or
not open for trading, is not a transient condition worth re-ingesting every
poll. That is the direct fix for the churn observed on 2026-08-30, where two
source signals cycled through the margin guard seven times.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Terminal statuses. Neither is retry-eligible.
UNSUPPORTED_SYMBOL_BLOCKED = "UNSUPPORTED_SYMBOL_BLOCKED"
SYMBOL_NOT_TRADING_BLOCKED = "SYMBOL_NOT_TRADING_BLOCKED"

#: What this system is allowed to trade.
REQUIRED_STATUS = "TRADING"
REQUIRED_CONTRACT_TYPE = "PERPETUAL"
REQUIRED_QUOTE_ASSET = "USDT"

_CACHE_TTL_SECONDS = 900

_lock = threading.Lock()
_markets: dict[str, dict[str, Any]] = {}
_fetched_at: float = 0.0


def _fetch(client: Any) -> dict[str, dict[str, Any]]:
    info = client._request("GET", "/fapi/v1/exchangeInfo", params={}, signed=False)
    symbols = info.get("symbols") or []
    if not symbols:
        raise RuntimeError("exchangeInfo returned no symbols")
    return {str(s.get("symbol")): s for s in symbols if s.get("symbol")}


def load_markets(client: Any, *, force: bool = False) -> dict[str, dict[str, Any]]:
    """Return cached exchangeInfo markets, refreshing when stale.

    Raises if metadata has never been loaded and cannot be fetched -- callers
    must fail closed rather than trade against unknown market rules. A refresh
    failure with a usable cache is tolerated and logged; the cache is only a
    few minutes stale and is still exchange-authoritative.
    """
    global _markets, _fetched_at
    with _lock:
        fresh = _markets and (time.time() - _fetched_at) < _CACHE_TTL_SECONDS
        if fresh and not force:
            return _markets
        try:
            _markets = _fetch(client)
            _fetched_at = time.time()
        except Exception as exc:
            if _markets:
                logger.warning(
                    "exchangeInfo refresh failed (%s); using cache from %.0fs ago",
                    exc, time.time() - _fetched_at,
                )
                return _markets
            raise
        return _markets


def resolve_market(client: Any, symbol: str) -> tuple[Optional[dict[str, Any]], Optional[str], Optional[str]]:
    """Validate ``symbol`` against exchange metadata.

    Returns ``(market, status, reason)``. On success ``status`` and ``reason``
    are None. On rejection ``market`` is None and ``status`` is one of the
    terminal statuses above.

    The symbol is matched exactly as the exchange spells it -- no display-name
    rewriting and no ticker guessing. Case is normalised because Binance
    symbols are upper-case for ASCII; characters with no case mapping are
    unaffected by ``str.upper()``.
    """
    candidate = (symbol or "").strip()
    if not candidate:
        return None, UNSUPPORTED_SYMBOL_BLOCKED, "empty symbol"
    candidate = candidate.upper()

    try:
        markets = load_markets(client)
    except Exception as exc:
        # No trustworthy metadata: refuse rather than assume the market is fine.
        return None, UNSUPPORTED_SYMBOL_BLOCKED, (
            f"exchange metadata unavailable, cannot verify {candidate}: {exc}"
        )

    market = markets.get(candidate)
    if market is None:
        return None, UNSUPPORTED_SYMBOL_BLOCKED, (
            f"{candidate} is not listed in Binance exchangeInfo"
        )

    status = str(market.get("status") or "")
    if status != REQUIRED_STATUS:
        return None, SYMBOL_NOT_TRADING_BLOCKED, (
            f"{candidate} is listed but status={status}, not {REQUIRED_STATUS}"
        )

    contract_type = str(market.get("contractType") or "")
    if contract_type != REQUIRED_CONTRACT_TYPE:
        return None, SYMBOL_NOT_TRADING_BLOCKED, (
            f"{candidate} contractType={contract_type}, not {REQUIRED_CONTRACT_TYPE}"
        )

    quote = str(market.get("quoteAsset") or "")
    if quote != REQUIRED_QUOTE_ASSET:
        return None, SYMBOL_NOT_TRADING_BLOCKED, (
            f"{candidate} quoteAsset={quote}, not {REQUIRED_QUOTE_ASSET}"
        )

    return market, None, None
