import asyncio
import json
import unittest

from src.trading.connectors.binance.user_data_stream import (
    BinanceUserDataStreamManager,
    SiblingLegRegistry,
)


class FakeListenKeyClient:
    def __init__(self):
        self.created = 0
        self.keepalives = []
        self.closed = []

    async def create_listen_key(self) -> str:
        self.created += 1
        return f"listen-key-{self.created}"

    async def keepalive_listen_key(self, listen_key: str) -> None:
        self.keepalives.append(listen_key)

    async def close_listen_key(self, listen_key: str) -> None:
        self.closed.append(listen_key)


class FakeAlgoOrderClient:
    def __init__(self):
        self.canceled = []

    async def cancel_algo_order(self, symbol: str, algo_id: int) -> None:
        self.canceled.append((symbol, algo_id))


class FakeWebSocket:
    """Yields queued messages, then blocks until closed."""

    def __init__(self, messages):
        self._messages = list(messages)
        self._closed = asyncio.Event()

    async def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        await self._closed.wait()
        raise ConnectionResetError("fake socket closed")

    async def close(self) -> None:
        self._closed.set()


def make_manager(**overrides) -> tuple[BinanceUserDataStreamManager, FakeListenKeyClient, FakeAlgoOrderClient]:
    listen_key_client = FakeListenKeyClient()
    algo_client = FakeAlgoOrderClient()
    manager = BinanceUserDataStreamManager(
        listen_key_client=listen_key_client,
        algo_order_client=algo_client,
        sibling_registry=SiblingLegRegistry(),
        **overrides,
    )
    return manager, listen_key_client, algo_client


def algo_update(algo_id: int, status: str, executed_qty: str, symbol: str = "BTCUSDT") -> str:
    return json.dumps({
        "e": "ALGO_UPDATE",
        "o": {"aid": algo_id, "s": symbol, "X": status, "aq": executed_qty},
    })


class TestAlgoUpdateHandling(unittest.IsolatedAsyncioTestCase):
    async def test_fill_cancels_sibling_leg(self):
        manager, _, algo_client = make_manager()
        manager.sibling_registry.register_pair("BTCUSDT", algo_id_a=111, algo_id_b=222)

        await manager._handle_message(algo_update(algo_id=111, status="FINISHED", executed_qty="0.50"))

        self.assertEqual(algo_client.canceled, [("BTCUSDT", 222)])

    async def test_cancel_without_fill_does_not_touch_sibling(self):
        manager, _, algo_client = make_manager()
        manager.sibling_registry.register_pair("BTCUSDT", algo_id_a=111, algo_id_b=222)

        # FINISHED with zero executed quantity = canceled/expired, not filled.
        await manager._handle_message(algo_update(algo_id=111, status="FINISHED", executed_qty="0.00000"))

        self.assertEqual(algo_client.canceled, [])

    async def test_non_terminal_status_ignored(self):
        manager, _, algo_client = make_manager()
        manager.sibling_registry.register_pair("BTCUSDT", algo_id_a=111, algo_id_b=222)

        await manager._handle_message(algo_update(algo_id=111, status="TRIGGERING", executed_qty="0"))
        await manager._handle_message(algo_update(algo_id=111, status="NEW", executed_qty="0"))

        self.assertEqual(algo_client.canceled, [])

    async def test_unregistered_algo_id_is_a_noop(self):
        manager, _, algo_client = make_manager()
        await manager._handle_message(algo_update(algo_id=999, status="FINISHED", executed_qty="1.0"))
        self.assertEqual(algo_client.canceled, [])

    async def test_pair_cleared_after_fill_so_second_leg_cannot_double_trigger(self):
        manager, _, algo_client = make_manager()
        manager.sibling_registry.register_pair("BTCUSDT", algo_id_a=111, algo_id_b=222)

        await manager._handle_message(algo_update(algo_id=111, status="FINISHED", executed_qty="0.50"))
        # The sibling (222) now also resolves FINISHED (from the cancel above,
        # so executed_qty is 0) — must not attempt to cancel 111 back.
        await manager._handle_message(algo_update(algo_id=222, status="FINISHED", executed_qty="0.00"))

        self.assertEqual(algo_client.canceled, [("BTCUSDT", 222)])


class TestAccountUpdateHandling(unittest.IsolatedAsyncioTestCase):
    async def test_account_update_invokes_callback(self):
        received = []

        async def on_update(event):
            received.append(event)

        manager, _, _ = make_manager(on_account_update=on_update)
        payload = json.dumps({"e": "ACCOUNT_UPDATE", "a": {"m": "ORDER"}})
        await manager._handle_message(payload)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["e"], "ACCOUNT_UPDATE")

    async def test_malformed_message_does_not_raise(self):
        manager, _, _ = make_manager()
        await manager._handle_message("not json")  # should log and return, not raise


class TestLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_start_creates_listen_key_and_stop_closes_it(self):
        ws = FakeWebSocket(messages=[])

        async def connector(url: str):
            return ws

        manager, listen_key_client, _ = make_manager(
            connector=connector,
            keepalive_interval_seconds=3600,  # don't fire during this test
        )

        await manager.start()
        await asyncio.sleep(0)  # let the run task reach the connector
        self.assertEqual(listen_key_client.created, 1)

        await manager.stop()
        self.assertEqual(listen_key_client.closed, ["listen-key-1"])

    async def test_keepalive_fires_on_its_interval(self):
        ws = FakeWebSocket(messages=[])

        async def connector(url: str):
            return ws

        manager, listen_key_client, _ = make_manager(
            connector=connector,
            keepalive_interval_seconds=0.01,
        )

        await manager.start()
        await asyncio.sleep(0.05)
        await manager.stop()

        self.assertGreaterEqual(len(listen_key_client.keepalives), 1)

    async def test_messages_are_processed_end_to_end_through_the_run_loop(self):
        payload = algo_update(algo_id=111, status="FINISHED", executed_qty="1.0")
        ws = FakeWebSocket(messages=[payload])

        async def connector(url: str):
            return ws

        manager, _, algo_client = make_manager(
            connector=connector,
            keepalive_interval_seconds=3600,
        )
        manager.sibling_registry.register_pair("BTCUSDT", algo_id_a=111, algo_id_b=222)

        await manager.start()
        await asyncio.sleep(0.02)
        await manager.stop()

        self.assertEqual(algo_client.canceled, [("BTCUSDT", 222)])


if __name__ == "__main__":
    unittest.main()
