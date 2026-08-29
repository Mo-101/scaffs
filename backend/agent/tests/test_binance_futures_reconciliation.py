import pytest
import hashlib
import sys
import os
from pathlib import Path

# Add backend/agent to sys.path
AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.connectors.binance.futures_sdk import (
    generate_deterministic_client_order_id,
    BinanceFuturesClient,
    BinanceFuturesConfig,
    BinanceAPIError,
    BinanceAmbiguousMutationError,
)
from src.trading.connectors.binance.classification import (
    classify_binance_mutation_error,
    BinanceOutcomeClass,
)


def test_deterministic_client_order_id_reproducibility():
    """Verify that identical decision parameters always generate the exact same CID."""
    cid_1 = generate_deterministic_client_order_id("BTCUSDT", "BUY", intent_id="intent_abc_123", quantity=0.01)
    cid_2 = generate_deterministic_client_order_id("BTCUSDT", "BUY", intent_id="intent_abc_123", quantity=0.01)
    assert cid_1 == cid_2
    assert len(cid_1) <= 36
    assert cid_1.startswith("sc_btcusd_b_")


def test_deterministic_client_order_id_distinct_on_different_decision():
    """Verify that different signals or intents produce distinct CIDs."""
    cid_buy = generate_deterministic_client_order_id("ETHUSDT", "BUY", signal_id="sig_001", quantity=0.1)
    cid_sell = generate_deterministic_client_order_id("ETHUSDT", "SELL", signal_id="sig_001", quantity=0.1)
    assert cid_buy != cid_sell


def test_market_order_cid_price_invariance():
    """Verify market orders ignore dynamic ticker estimates and use stable digest placeholder."""
    cid_mkt_1 = generate_deterministic_client_order_id("ETHUSDT", "BUY", quantity=0.01, price=None)
    cid_mkt_2 = generate_deterministic_client_order_id("ETHUSDT", "BUY", quantity=0.01, price=None)
    assert cid_mkt_1 == cid_mkt_2


def test_outcome_classification_matrix():
    """Verify that all exchange codes and transport errors are correctly classified."""
    cases = [
        (-1021, "Timestamp for this request is outside of the recvWindow.", BinanceOutcomeClass.RECONCILE_REQUIRED),
        (-2010, "Account has insufficient balance for requested action.", BinanceOutcomeClass.TERMINAL_REJECT),
        (-2011, "Unknown order sent.", BinanceOutcomeClass.RECONCILE_REQUIRED),
        (-2013, "Order does not exist.", BinanceOutcomeClass.RECONCILE_REQUIRED),
        (-4131, "PERCENT_PRICE filter limit exceeded.", BinanceOutcomeClass.RECONCILE_REQUIRED),
        (-1003, "Too many requests.", BinanceOutcomeClass.RATE_LIMITED),
        (None, "Read timed out after 10 seconds", BinanceOutcomeClass.RECONCILE_REQUIRED),
    ]
    for code, msg, expected_cls in cases:
        is_timeout = code is None
        res = classify_binance_mutation_error(code, msg, is_network_timeout=is_timeout)
        assert res == expected_cls, f"Failed for code {code}: got {res}, expected {expected_cls}"


def test_reconciliation_on_transport_timeout_simulation():
    """Verify that when a transport drop occurs after sending, the SDK reconciles via CID."""
    cfg = BinanceFuturesConfig(api_key="mock_key", api_secret="mock_secret", testnet_host="https://mock.testnet")
    client = BinanceFuturesClient(cfg)

    # Mock order returned by secondary status query
    mock_filled_order = {
        "orderId": 888888,
        "symbol": "ETHUSDT",
        "status": "FILLED",
        "clientOrderId": "sc_ethusd_b_mock_cid",
        "executedQty": "0.010",
        "avgPrice": "2500.00",
    }

    call_count = 0

    def mock_request(method, endpoint, params=None, signed=False):
        nonlocal call_count
        call_count += 1
        if method == "POST" and endpoint == "/fapi/v1/order":
            # Simulate network timeout on return
            raise BinanceAPIError(
                msg="Network transport failure (mock timeout)",
                code=None,
                http_status=None,
                outcome_class=BinanceOutcomeClass.RECONCILE_REQUIRED,
                is_timeout=True,
            )
        elif method == "GET" and endpoint == "/fapi/v1/order":
            return mock_filled_order
        elif method == "GET" and endpoint == "/fapi/v1/exchangeInfo":
            call_count -= 1
            return {
                "symbols": [
                    {
                        "symbol": "ETHUSDT",
                        "quantityPrecision": 3,
                        "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}],
                    }
                ]
            }
        raise ValueError(f"Unexpected endpoint {endpoint}")

    client._request = mock_request
    client._exchange_info = {
        "symbols": [
            {
                "symbol": "ETHUSDT",
                "quantityPrecision": 3,
                "filters": [{"filterType": "LOT_SIZE", "stepSize": "0.001"}],
            }
        ]
    }

    result = client.place_order(
        symbol="ETHUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        intent_id="intent_mock_timeout",
    )

    assert result["ok"] is True
    assert result["reconciled"] is True
    assert result["order"]["status"] == "FILLED"
    assert result["outcome_class"] == "success"
    assert call_count == 2  # 1 POST attempt + 1 GET reconciliation query
