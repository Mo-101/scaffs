"""Live Binance Testnet account/position state for the Step 4 risk gate."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Sequence

from .pre_trade import AccountSnapshot, PositionSnapshot
from ..connectors.binance.futures_sdk import BinanceFuturesClient

logger = logging.getLogger(__name__)


class BinanceTestnetStateProvider:
    """Adapts the Binance Futures SDK into the Step 4 BinanceStateProvider protocol."""

    def __init__(self, client: BinanceFuturesClient) -> None:
        self.client = client
        self.mode = "testnet"
        self.host = str(client.config.base_url).rstrip("/").lower()
        self.is_testnet = bool(client.config.is_testnet)

    def account_snapshot(self) -> AccountSnapshot:
        info = self.client.get_account_information()
        available = Decimal(str(info.get("availableBalance", 0.0)))
        return AccountSnapshot(available_balance_usdt=available, status="OK")

    def positions(self) -> tuple[str, Sequence[PositionSnapshot]]:
        raw_positions = self.client.get_positions()
        positions: list[PositionSnapshot] = []
        for raw in raw_positions:
            try:
                symbol = str(raw.get("symbol", "")).upper()
                notional = Decimal(str(raw.get("notionalValue", "0")))
                # positionRisk sometimes returns notional as signed; if not,
                # fall back to positionAmt * markPrice.
                if notional == 0:
                    amt = Decimal(str(raw.get("positionAmt", "0")))
                    price = Decimal(str(raw.get("markPrice", raw.get("entryPrice", "0"))))
                    notional = amt * price
                leverage = Decimal(str(raw.get("leverage", "1")))
                positions.append(
                    PositionSnapshot(
                        symbol=symbol,
                        signed_notional_usdt=notional,
                        leverage=leverage,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse Binance position: %s", exc)
                return ("ERROR", [])
        return ("OK", positions)
