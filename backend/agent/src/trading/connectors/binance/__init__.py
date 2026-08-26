"""Binance trading connector (Spot and USD-M Futures Testnet)."""

from .futures_sdk import (
    DEFAULT_FUTURES_TESTNET_HOST,
    BinanceFuturesClient,
    BinanceFuturesConfig,
    get_binance_futures_client,
)
from .sdk import (
    BinanceConfig,
    check_status,
    get_account_snapshot,
    get_historical_bars,
    get_open_orders,
    get_positions,
    get_quote,
    place_order,
    cancel_order,
)

__all__ = [
    "BinanceConfig",
    "BinanceFuturesClient",
    "BinanceFuturesConfig",
    "DEFAULT_FUTURES_TESTNET_HOST",
    "get_binance_futures_client",
    "check_status",
    "get_account_snapshot",
    "get_positions",
    "get_open_orders",
    "get_quote",
    "get_historical_bars",
    "place_order",
    "cancel_order",
]
