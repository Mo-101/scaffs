"""Load Step 4 risk-gate configuration from the environment."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from .pre_trade import RiskConfig


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def load_risk_config() -> RiskConfig:
    """Return a ``RiskConfig`` populated from environment variables."""
    allowed_symbols_raw = (os.getenv("ALLOWED_SYMBOLS") or "BTC-USDT,ETH-USDT").split(",")
    allowed_symbols = frozenset(
        s.strip().upper().replace("-", "").replace("/", "")
        for s in allowed_symbols_raw
        if s.strip()
    )
    return RiskConfig(
        max_trade_notional_usdt=_d(os.getenv("MAX_TRADE_NOTIONAL_USDT") or 1000),
        max_position_notional_usdt=_d(os.getenv("MAX_POSITION_NOTIONAL_USDT") or 2000),
        max_leverage=_d(os.getenv("MAX_LEVERAGE") or 5),
        min_available_balance_usdt=_d(os.getenv("MIN_AVAILABLE_BALANCE_USDT") or 100),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS") or 3),
        trade_cooldown_seconds=int(os.getenv("TRADE_COOLDOWN_SECONDS") or 60),
        allowed_symbols=allowed_symbols,
        max_market_data_age_seconds=int(os.getenv("MAX_MARKET_DATA_AGE_SECONDS") or 60),
    )
