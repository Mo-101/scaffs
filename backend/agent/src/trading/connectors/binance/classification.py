"""Curated read/write classification and outcome classifier for Binance operations.

Keys are the ccxt unified method names and Binance futures endpoints. Order-mutating
calls are pinned WRITE so the live gate never treats them as plain reads.
Outcome classification routes error codes (-1021, -2013, -2011, -4131, etc.)
and network transport drops through deterministic reconciliation paths.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional

from src.live.classification import ToolClass

#: Binance (ccxt) spot operation read/write catalog.
BINANCE_TOOL_CLASS: dict[str, ToolClass] = {
    # READ
    "fetch_balance": ToolClass.READ,
    "fetch_open_orders": ToolClass.READ,
    "fetch_my_trades": ToolClass.READ,
    "fetch_ticker": ToolClass.READ,
    "fetch_ohlcv": ToolClass.READ,
    # WRITE
    "create_order": ToolClass.WRITE,
    "cancel_order": ToolClass.WRITE,
}


class BinanceOutcomeClass(str, Enum):
    """Canonical classification for order mutation outcomes."""
    SUCCESS = "success"
    RECONCILE_REQUIRED = "reconcile_required"
    TERMINAL_REJECT = "terminal_reject"
    RATE_LIMITED = "rate_limited"
    UNKNOWN_ERROR = "unknown_error"


#: Binance REST error codes mapped to outcome classes
# -1021 (Timestamp drift): Transport condition requiring clock resync and order status query.
# -2013 (Order does not exist): Context-sensitive; order may already be filled or canceled.
# -2011 (Unknown order / cancel rejected): Requires status query reconciliation.
# -4131 (Expired due to price protection): Requires order state query reconciliation.
# -2010 (Insufficient balance): Definitive pre-matching rejection.
# -1003 (Rate limit exceeded / IP banned): Throttle and backoff.
BINANCE_ERROR_OUTCOME_MAP: dict[int, BinanceOutcomeClass] = {
    -1021: BinanceOutcomeClass.RECONCILE_REQUIRED,   # Timestamp outside receive window / clock drift
    -2013: BinanceOutcomeClass.RECONCILE_REQUIRED,   # Order does not exist (may be filled/canceled)
    -2011: BinanceOutcomeClass.RECONCILE_REQUIRED,   # Cancel rejected / unknown order
    -4131: BinanceOutcomeClass.RECONCILE_REQUIRED,   # Expired due to price protection
    -2010: BinanceOutcomeClass.TERMINAL_REJECT,      # Account has insufficient balance
    -1100: BinanceOutcomeClass.TERMINAL_REJECT,      # Illegal characters in parameter
    -1102: BinanceOutcomeClass.TERMINAL_REJECT,      # Mandatory parameter empty or malformed
    -1003: BinanceOutcomeClass.RATE_LIMITED,         # Rate limit exceeded / IP banned
}


def classify_binance_mutation_error(
    code: Optional[int],
    message: str = "",
    http_status: Optional[int] = None,
    is_network_timeout: bool = False,
) -> BinanceOutcomeClass:
    """Classify an error arising from an order mutation on Binance.

    Args:
        code: The Binance error code integer (e.g. -1021, -2013), if provided.
        message: The error description string.
        http_status: The HTTP status code (e.g. 504, 502, 400).
        is_network_timeout: True if request timed out or connection was aborted after sending.

    Returns:
        The resolved BinanceOutcomeClass.
    """
    if is_network_timeout or (http_status is not None and http_status in (502, 503, 504)):
        return BinanceOutcomeClass.RECONCILE_REQUIRED

    if code is not None and code in BINANCE_ERROR_OUTCOME_MAP:
        return BINANCE_ERROR_OUTCOME_MAP[code]

    if http_status is not None and http_status >= 500:
        return BinanceOutcomeClass.RECONCILE_REQUIRED

    return BinanceOutcomeClass.UNKNOWN_ERROR

