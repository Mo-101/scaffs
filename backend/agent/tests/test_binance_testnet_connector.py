import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

agent_dir = Path(__file__).resolve().parent.parent
backend_dir = agent_dir.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

from src.trading.connectors.binance.classification import (
    BinanceOutcomeClass,
    classify_binance_mutation_error,
)
from src.trading.connectors.binance.futures_sdk import (
    BinanceAPIError,
    BinanceAmbiguousMutationError,
    BinanceFuturesClient,
    BinanceFuturesConfig,
    DEFAULT_FUTURES_TESTNET_HOST,
    generate_deterministic_client_order_id,
    get_binance_futures_client,
)

def test_binance_error_classifier():
    # -1021 (Timestamp drift / clock skew) -> RECONCILE_REQUIRED (transport condition, not terminal)
    assert classify_binance_mutation_error(-1021) == BinanceOutcomeClass.RECONCILE_REQUIRED
    # -2013 (Order does not exist) -> RECONCILE_REQUIRED (may already be filled or canceled)
    assert classify_binance_mutation_error(-2013) == BinanceOutcomeClass.RECONCILE_REQUIRED
    # -2011 (Cancel rejected / unknown order) -> RECONCILE_REQUIRED
    assert classify_binance_mutation_error(-2011) == BinanceOutcomeClass.RECONCILE_REQUIRED
    # -4131 (Expired due to price protection) -> RECONCILE_REQUIRED
    assert classify_binance_mutation_error(-4131) == BinanceOutcomeClass.RECONCILE_REQUIRED
    # -2010 (Insufficient balance) -> TERMINAL_REJECT
    assert classify_binance_mutation_error(-2010) == BinanceOutcomeClass.TERMINAL_REJECT
    # -1003 (Rate limit exceeded) -> RATE_LIMITED
    assert classify_binance_mutation_error(-1003) == BinanceOutcomeClass.RATE_LIMITED
    # 504 Gateway Timeout -> RECONCILE_REQUIRED
    assert classify_binance_mutation_error(None, http_status=504) == BinanceOutcomeClass.RECONCILE_REQUIRED
    # Network timeout -> RECONCILE_REQUIRED
    assert classify_binance_mutation_error(None, is_network_timeout=True) == BinanceOutcomeClass.RECONCILE_REQUIRED

def test_deterministic_idempotency_key():
    k1 = generate_deterministic_client_order_id("BTCUSDT", "BUY", intent_id="mandate_1001")
    k2 = generate_deterministic_client_order_id("BTC/USDT", "BUY", intent_id="mandate_1001")
    assert k1 == k2
    assert k1.startswith("sc_btcusd_b_")

def test_binance_futures_config():
    cfg = BinanceFuturesConfig(
        api_key="test_key_123",
        api_secret="test_secret_abc",
        is_testnet=True,
    )
    assert cfg.api_key == "test_key_123"
    assert cfg.is_testnet is True
    assert cfg.base_url == DEFAULT_FUTURES_TESTNET_HOST

def test_binance_futures_signature():
    cfg = BinanceFuturesConfig(
        api_key="test_key",
        api_secret="test_secret",
    )
    client = BinanceFuturesClient(cfg)
    sig = client._sign({"symbol": "BTCUSDT", "timestamp": 1234567890})
    assert isinstance(sig, str)
    assert len(sig) == 64

@patch("urllib.request.urlopen")
def test_binance_futures_ping(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"{}"
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = BinanceFuturesClient(BinanceFuturesConfig(testnet_host=DEFAULT_FUTURES_TESTNET_HOST))
    res = client.ping()
    assert res == {}

@patch("urllib.request.urlopen")
def test_binance_futures_get_server_time(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"serverTime": 1740000000000}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    client = BinanceFuturesClient(BinanceFuturesConfig(testnet_host=DEFAULT_FUTURES_TESTNET_HOST))
    server_time = client.get_server_time()
    assert server_time == 1740000000000

@patch("urllib.request.urlopen")
def test_binance_futures_get_account_balance(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'[{"asset": "USDT", "balance": "10000.00", "availableBalance": "10000.00"}]'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    balances = client.get_account_balance()
    assert len(balances) == 1
    assert balances[0]["asset"] == "USDT"
    assert float(balances[0]["balance"]) == 10000.0

@patch("urllib.request.urlopen")
def test_binance_futures_place_order_success(mock_urlopen):
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"orderId": 987654321, "symbol": "BTCUSDT", "status": "NEW", "side": "BUY", "type": "MARKET"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    res = client.place_order(symbol="BTC/USDT", side="BUY", order_type="MARKET", quantity=0.01)
    assert res["ok"] is True
    assert res["order"]["orderId"] == 987654321
    assert res["outcome_class"] == BinanceOutcomeClass.SUCCESS.value

@patch.object(BinanceFuturesClient, "get_order")
@patch.object(BinanceFuturesClient, "_request")
def test_binance_futures_place_order_reconcile_on_1021(mock_req, mock_get_order):
    # Simulate -1021 Timestamp drift error on order post
    mock_req.side_effect = BinanceAPIError(
        msg="Timestamp outside recvWindow",
        code=-1021,
        http_status=400,
        outcome_class=BinanceOutcomeClass.RECONCILE_REQUIRED,
    )
    # Status query confirms order actually landed and was FILLED
    mock_get_order.return_value = {"orderId": 112233, "status": "FILLED", "symbol": "BTCUSDT"}

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    import time
    client._exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "quantityPrecision": 3,
                "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}],
            }
        ]
    }
    client._exchange_info_at = time.time()
    res = client.place_order(symbol="BTCUSDT", side="BUY", quantity=0.01, client_order_id="scaffs_test_1")
    assert res["ok"] is True
    assert res["reconciled"] is True
    assert res["order"]["orderId"] == 112233
    assert res["order"]["status"] == "FILLED"

@patch.object(BinanceFuturesClient, "get_order")
@patch.object(BinanceFuturesClient, "_request")
def test_binance_futures_cancel_reconciliation_on_2013(mock_req, mock_get_order):
    # Simulate -2013 Order does not exist on cancel
    mock_req.side_effect = BinanceAPIError(
        msg="Order does not exist",
        code=-2013,
        http_status=400,
        outcome_class=BinanceOutcomeClass.RECONCILE_REQUIRED,
    )
    # Status query shows it was already FILLED
    mock_get_order.return_value = {"orderId": 445566, "status": "FILLED", "symbol": "BTCUSDT"}

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    res = client.cancel_order(symbol="BTCUSDT", order_id=445566)
    assert res["ok"] is True
    assert res["canceled"] is False
    assert res["status"] == "FILLED"

@patch.object(BinanceFuturesClient, "get_order")
@patch.object(BinanceFuturesClient, "_request")
def test_binance_futures_cancel_reconciliation_on_4131(mock_req, mock_get_order):
    # Simulate -4131 Expired due to price protection
    mock_req.side_effect = BinanceAPIError(
        msg="Order expired due to price protection",
        code=-4131,
        http_status=400,
        outcome_class=BinanceOutcomeClass.RECONCILE_REQUIRED,
    )
    mock_get_order.return_value = {"orderId": 778899, "status": "EXPIRED", "symbol": "BTCUSDT"}

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    res = client.cancel_order(symbol="BTCUSDT", order_id=778899)
    assert res["ok"] is True
    assert res["canceled"] is True
    assert res["status"] == "EXPIRED"

@patch.object(BinanceFuturesClient, "_request")
def test_binance_futures_place_order_terminal_reject_on_2010(mock_req):
    # Simulate -2010 Insufficient balance -> terminal reject (does not trigger reconciliation)
    mock_req.side_effect = BinanceAPIError(
        msg="Account has insufficient balance",
        code=-2010,
        http_status=400,
        outcome_class=BinanceOutcomeClass.TERMINAL_REJECT,
    )

    cfg = BinanceFuturesConfig(api_key="key", api_secret="secret")
    client = BinanceFuturesClient(cfg)
    with pytest.raises(BinanceAPIError) as exc_info:
        client.place_order(symbol="BTCUSDT", side="BUY", quantity=100.0)
    assert exc_info.value.code == -2010
    assert exc_info.value.outcome_class == BinanceOutcomeClass.TERMINAL_REJECT

def test_paper_routes_governance_hard_cap(monkeypatch):
    from fastapi.testclient import TestClient
    from api_server import app

    # The route validates the runtime env after any .env files are loaded.
    # Override with a safe testnet-only configuration.
    monkeypatch.setenv("BINANCE_TRADING_MODE", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_HOST", "https://testnet.binancefuture.com")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)

    client = TestClient(app, client=("127.0.0.1", 50000))
    # Placing an order exceeding $100.00 USD hard cap must be rejected with 400
    res = client.post(
        "/paper-sessions/binance-testnet/order",
        json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 1.0, "price": 50000.0},
    )
    assert res.status_code == 400
    assert "exceeds hard governance limit" in res.json().get("detail", "")

    # Supplying leverage or margin_type directly to the order path must be rejected with 400
    res_decoupled = client.post(
        "/paper-sessions/binance-testnet/order",
        json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "leverage": 10},
    )
    assert res_decoupled.status_code == 400
    assert "Account leverage/margin mutations are decoupled" in res_decoupled.json().get("detail", "")


def test_paper_routes_market_order_type_rejected(monkeypatch):
    """Every entry in this system is a resting LIMIT order now; an explicit
    order_type=MARKET must be rejected rather than silently converted."""
    from fastapi.testclient import TestClient
    from api_server import app

    monkeypatch.setenv("BINANCE_TRADING_MODE", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_HOST", "https://testnet.binancefuture.com")
    monkeypatch.delenv("API_AUTH_KEY", raising=False)

    client = TestClient(app, client=("127.0.0.1", 50000))
    res = client.post(
        "/paper-sessions/binance-testnet/order",
        json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "price": 50000.0, "order_type": "MARKET"},
    )
    assert res.status_code == 400
    assert "not supported" in res.json().get("detail", "")


class _FakeManualOrderClient:
    """Minimal fake covering exactly what place_binance_testnet_order and the
    signal-queue dispatch pipeline it now routes through need."""

    def __init__(self, margin_type="ISOLATED", leverage=5, positions=None):
        self._margin_type = margin_type
        self._leverage = leverage
        self._positions = positions if positions is not None else []

    def get_ticker_price(self, symbol):
        return 50000.0

    def get_positions(self, symbol=None):
        return self._positions

    def get_symbol_margin_type(self, symbol):
        return self._margin_type

    def set_margin_type(self, symbol, margin_type="ISOLATED"):
        return {"code": 200}

    def get_symbol_leverage(self, symbol):
        return self._leverage

    def set_leverage(self, symbol, leverage):
        return {"leverage": leverage}

    def get_quantity_precision(self, symbol):
        return 3

    def get_price_tick_size(self, symbol):
        return 0.01

    def get_order(self, symbol=None, order_id=None, client_order_id=None):
        return {"status": "NEW", "executedQty": "0"}

    def get_order_trades(self, symbol, order_id):
        return []


class _FakeManualOrderExecutor:
    last_intent = None

    def __init__(self, client):
        self.client = client
        self.execution_enabled = False

    def submit(self, intent, session_dir=None):
        from src.trading.trade_intent import ExecutionResult

        _FakeManualOrderExecutor.last_intent = intent
        return ExecutionResult(intent_id=intent.intent_id, status="SUBMITTED", exchange_order_id="fake-manual-1")


def _testnet_env(monkeypatch):
    monkeypatch.setenv("BINANCE_TRADING_MODE", "testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_HOST", "https://testnet.binancefuture.com")
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")


def test_manual_order_routes_through_signal_queue_pipeline(monkeypatch):
    """The direct order endpoint no longer calls client.place_order itself --
    it must reach the SAME gateway (enqueue_signal + dispatch_queued_signal)
    as /signal-queue/dispatch, gaining collision/margin/leverage/risk-gate
    parity for free instead of duplicating checks."""
    import src.trading.connectors.binance.futures_sdk as futures_sdk_module
    import src.trading.connectors.binance.binance_testnet_executor as bte_module
    from fastapi.testclient import TestClient
    from api_server import app

    _testnet_env(monkeypatch)
    fake_client = _FakeManualOrderClient()
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", _FakeManualOrderExecutor)
    _FakeManualOrderExecutor.last_intent = None

    client = TestClient(app, client=("127.0.0.1", 50000))
    # quantity(0.001) * price(50000) = $50 notional -- previously this exact
    # combination would have spuriously tripped dispatch_queued_signal's
    # NOTIONAL_STEP_TOO_COARSE check against its 100.0 default if notional_usd
    # weren't derived from the order's own price/quantity.
    res = client.post(
        "/paper-sessions/binance-testnet/order",
        json={
            "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "price": 50000.0,
            "stop_loss": 48000.0, "take_profit": 52000.0,
        },
    )
    body = res.json()
    assert res.status_code == 200
    assert body["ok"] is True
    # No more raw Binance "order" key -- the new response is the dispatch dict.
    assert "order" not in body
    assert body["status"] in ("DISPATCHED", "PARTIALLY_FILLED", "PROTECTED")
    assert "governance" in body

    intent = _FakeManualOrderExecutor.last_intent
    assert intent is not None
    assert intent.order_type == "LIMIT"
    assert intent.stop_loss == 48000.0
    assert intent.take_profit == 52000.0


def test_manual_order_margin_mismatch_reachable(monkeypatch):
    """Full parity: a margin-mode mismatch is now caught via the same
    dispatch_queued_signal gate the signal queue uses, returned as a normal
    200/ok:false body (not a bespoke 409 from a standalone check)."""
    import src.trading.connectors.binance.futures_sdk as futures_sdk_module
    import src.trading.connectors.binance.binance_testnet_executor as bte_module
    from fastapi.testclient import TestClient
    from api_server import app

    _testnet_env(monkeypatch)
    fake_client = _FakeManualOrderClient(margin_type="CROSSED")
    monkeypatch.setattr(futures_sdk_module, "get_binance_futures_client", lambda *a, **k: fake_client)
    monkeypatch.setattr(bte_module, "BinanceTestnetExecutor", _FakeManualOrderExecutor)
    _FakeManualOrderExecutor.last_intent = None

    client = TestClient(app, client=("127.0.0.1", 50000))
    res = client.post(
        "/paper-sessions/binance-testnet/order",
        json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.001, "price": 50000.0},
    )
    body = res.json()
    assert res.status_code == 200
    assert body["ok"] is False
    assert body["status"] == "MARGIN_MODE_MISMATCH_BLOCKED"
    assert _FakeManualOrderExecutor.last_intent is None  # never reached the executor


