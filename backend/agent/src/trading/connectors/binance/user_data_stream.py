"""
user_data_stream.py

Binance USDS-M Futures user-data WebSocket stream manager.

Purpose: react to fills/cancels on TP/SL legs in sub-second time by listening
to ALGO_UPDATE (conditional/algo order lifecycle) and ACCOUNT_UPDATE (position/
margin) events, instead of waiting on the REST reconciler's ~15s sweep.

IMPORTANT — Algo Service migration (Binance, effective 2025-12-09):
STOP_MARKET / TAKE_PROFIT_MARKET / STOP / TAKE_PROFIT / TRAILING_STOP_MARKET
orders on USDS-M Futures no longer go through the classic order endpoints —
POST /fapi/v1/order now returns -4120 STOP_ORDER_SWITCH_ALGO for these types.
They are placed via POST /fapi/v1/algoOrder and canceled via
DELETE /fapi/v1/algoOrder, identified by `algoId` (not `orderId`). This module
assumes your SL/TP legs are already placed as algo orders for that reason —
if futures_sdk.py still places them via the classic endpoint, fix that first;
this stream will otherwise listen for an event type that never arrives
because the orders it's meant to protect were never accepted in the first
place (or are erroring out with -4120 right now).

Sibling-cancel safety note: Binance overloads the terminal algoStatus
"FINISHED" for BOTH "filled" and "canceled" outcomes (see Event Algo Order
Update docs). This module treats an order as filled only when FINISHED
arrives with executed quantity ("aq") > 0. Getting this backwards is not
cosmetic: canceling the surviving leg because the OTHER leg was itself
canceled (not filled) strips the position of its only remaining protection.
Verify "aq" semantics against live payloads (paper first) before trusting
this — it deserves a canary run, not just the unit tests here.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)

TESTNET_WS_BASE = "wss://stream.binancefuture.com/ws"
MAINNET_WS_BASE = "wss://fstream.binance.com/ws"
LISTEN_KEY_KEEPALIVE_INTERVAL_SECONDS = 30 * 60  # Binance requires a PUT within 60 min
RECONNECT_BASE_DELAY_SECONDS = 1.0
RECONNECT_MAX_DELAY_SECONDS = 60.0


class FuturesListenKeyClient(Protocol):
    """Seam to futures_sdk.py — names match the plan's section 2 spec."""

    async def create_listen_key(self) -> str: ...
    async def keepalive_listen_key(self, listen_key: str) -> None: ...
    async def close_listen_key(self, listen_key: str) -> None: ...


class FuturesAlgoOrderClient(Protocol):
    """DELETE /fapi/v1/algoOrder, keyed by algoId."""

    async def cancel_algo_order(self, symbol: str, algo_id: int) -> None: ...


class WebSocketConnection(Protocol):
    """Matches the subset of `websockets` connection interface this module needs."""

    async def recv(self) -> str: ...
    async def close(self) -> None: ...


WebSocketConnector = Callable[[str], Awaitable[WebSocketConnection]]


@dataclass
class SiblingLegRegistry:
    """Maps one leg's algoId to its sibling (the other leg of a TP/SL bracket)."""

    _siblings: Dict[int, Tuple[str, int]] = field(default_factory=dict)

    def register_pair(self, symbol: str, algo_id_a: int, algo_id_b: int) -> None:
        self._siblings[algo_id_a] = (symbol, algo_id_b)
        self._siblings[algo_id_b] = (symbol, algo_id_a)

    def sibling_of(self, algo_id: int) -> Optional[Tuple[str, int]]:
        return self._siblings.get(algo_id)

    def clear_pair(self, algo_id: int) -> None:
        pair = self._siblings.pop(algo_id, None)
        if pair is not None:
            self._siblings.pop(pair[1], None)


@dataclass
class BinanceUserDataStreamManager:
    listen_key_client: FuturesListenKeyClient
    algo_order_client: FuturesAlgoOrderClient
    sibling_registry: SiblingLegRegistry
    on_account_update: Optional[Callable[[dict], Awaitable[None]]] = None
    use_testnet: bool = True  # safe default while ENABLE_LIVE_TRADING=false
    connector: Optional[WebSocketConnector] = None  # wire to `websockets.connect` in api_server.py
    keepalive_interval_seconds: float = LISTEN_KEY_KEEPALIVE_INTERVAL_SECONDS
    reconnect_base_delay_seconds: float = RECONNECT_BASE_DELAY_SECONDS
    reconnect_max_delay_seconds: float = RECONNECT_MAX_DELAY_SECONDS

    _listen_key: Optional[str] = field(default=None, init=False)
    _ws: Optional[WebSocketConnection] = field(default=None, init=False)
    _keepalive_task: Optional[asyncio.Task] = field(default=None, init=False)
    _run_task: Optional[asyncio.Task] = field(default=None, init=False)
    _stopping: bool = field(default=False, init=False)

    def _ws_base(self) -> str:
        return TESTNET_WS_BASE if self.use_testnet else MAINNET_WS_BASE

    async def start(self) -> None:
        self._stopping = False
        self._listen_key = await self.listen_key_client.create_listen_key()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        self._run_task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stopping = True
        for task in (self._keepalive_task, self._run_task):
            if task is not None:
                task.cancel()
        if self._ws is not None:
            await self._ws.close()
        if self._listen_key is not None:
            await self.listen_key_client.close_listen_key(self._listen_key)

    async def _keepalive_loop(self) -> None:
        try:
            while not self._stopping:
                await asyncio.sleep(self.keepalive_interval_seconds)
                if self._stopping or self._listen_key is None:
                    return
                try:
                    await self.listen_key_client.keepalive_listen_key(self._listen_key)
                except Exception:
                    logger.exception(
                        "listenKey keepalive failed; stream will likely need "
                        "to reconnect with a fresh key"
                    )
        except asyncio.CancelledError:
            pass

    async def _run_forever(self) -> None:
        delay = self.reconnect_base_delay_seconds
        try:
            while not self._stopping:
                try:
                    await self._connect_and_consume()
                    delay = self.reconnect_base_delay_seconds  # reset after a clean session
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("user-data stream dropped; reconnecting with backoff")
                    if self._listen_key is not None:
                        try:
                            self._listen_key = await self.listen_key_client.create_listen_key()
                        except Exception:
                            logger.exception("failed to reissue listenKey during reconnect")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self.reconnect_max_delay_seconds)
        except asyncio.CancelledError:
            pass

    async def _connect_and_consume(self) -> None:
        if self.connector is None:
            raise RuntimeError(
                "no WebSocket connector configured — wire `connector` to "
                "`websockets.connect` (or your preferred client) in api_server.py"
            )
        url = f"{self._ws_base()}/{self._listen_key}"
        self._ws = await self.connector(url)
        try:
            while not self._stopping:
                raw = await self._ws.recv()
                await self._handle_message(raw)
        finally:
            await self._ws.close()
            self._ws = None

    async def _handle_message(self, raw: str) -> None:
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            logger.warning("could not parse user-data stream message: %r", raw)
            return

        event_type = event.get("e")
        if event_type == "ACCOUNT_UPDATE":
            if self.on_account_update is not None:
                await self.on_account_update(event)
        elif event_type == "ALGO_UPDATE":
            await self._handle_algo_update(event)
        else:
            logger.debug("unhandled user-data stream event type: %s", event_type)

    async def _handle_algo_update(self, event: dict) -> None:
        order = event.get("o", {})
        algo_id = order.get("aid")
        algo_status = order.get("X")
        executed_qty_raw = order.get("aq", "0")

        if algo_id is None or algo_status != "FINISHED":
            return

        try:
            executed_qty = float(executed_qty_raw)
        except (TypeError, ValueError):
            executed_qty = 0.0

        was_filled = executed_qty > 0.0
        if not was_filled:
            # Terminal but not a fill (canceled/expired without executing)
            self.sibling_registry.clear_pair(algo_id)
            return

        sibling = self.sibling_registry.sibling_of(algo_id)
        self.sibling_registry.clear_pair(algo_id)
        if sibling is None:
            return

        sibling_symbol, sibling_algo_id = sibling
        try:
            await self.algo_order_client.cancel_algo_order(sibling_symbol, sibling_algo_id)
        except Exception:
            logger.exception(
                "failed to cancel sibling algo order %s for %s after leg %s "
                "filled — manual intervention needed to avoid a naked leg",
                sibling_algo_id, sibling_symbol, algo_id,
            )
