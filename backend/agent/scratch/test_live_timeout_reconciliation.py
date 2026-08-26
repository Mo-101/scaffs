import sys
import json
import urllib.error
from dotenv import load_dotenv

load_dotenv("/home/idona/MoStar/scaffs/.env")
sys.path.insert(0, "/home/idona/MoStar/scaffs/backend/agent")

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client, BinanceOutcomeClass

client = get_binance_futures_client()

print("================================================================================")
print("LIVE FAULT INJECTION: POST-SEND NETWORK TIMEOUT & AMBIGUOUS RECONCILIATION")
print("================================================================================")

# Save original _request method
real_request = client._request

# Flag to simulate timeout only on the first POST /fapi/v1/order call
injected = False

def fault_injected_request(method, endpoint, params=None, signed=False):
    global injected
    if method.upper() == "POST" and endpoint == "/fapi/v1/order" and not injected:
        print("[FAULT INJECTOR] Transmitting order to Binance matching engine...")
        # Actually execute the real network write so the order is placed on Binance
        real_response = real_request(method, endpoint, params=params, signed=signed)
        injected = True
        print(f"[FAULT INJECTOR] Order successfully reached Binance (Order ID: {real_response.get('orderId')}).")
        print("[FAULT INJECTOR] SIMULATING TRANSPORT DROP: Dropping response packet / raising ReadTimeout!")
        # Simulate network timeout after send
        outcome_class = BinanceOutcomeClass.RECONCILE_REQUIRED
        from src.trading.connectors.binance.futures_sdk import BinanceAPIError
        raise BinanceAPIError(
            msg="Network transport failure connecting to Binance Futures (https://testnet.binancefuture.com/fapi/v1/order): <urlopen error timed out>",
            code=None,
            http_status=None,
            outcome_class=outcome_class,
            is_timeout=True,
        )
    # Subsequent calls (like GET /fapi/v1/order for status reconciliation) pass through normally
    return real_request(method, endpoint, params=params, signed=signed)

# Monkeypatch the client request method
client._request = fault_injected_request

intent_id = "test_intent_timeout_reconcile_404"
print(f"Submitting BUY 0.01 ETHUSDT with intent_id='{intent_id}'...")

try:
    result = client.place_order(
        symbol="ETHUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.01,
        intent_id=intent_id,
    )
    print("\n[SUCCESS] SDK Reconciler Handled Transport Timeout Gracefully!")
    print("Reconciled Result Returned to Caller:")
    print(json.dumps(result, indent=2))
    
    assert result.get("ok") is True, "Result ok must be True"
    assert result.get("reconciled") is True, "reconciled flag must be True"
    assert result.get("order", {}).get("status") in ("NEW", "FILLED"), "Order status must be confirmed"
    print("\n-> RESULT: PASS. Reconciler seamlessly verified the ambiguous order via deterministic clientOrderId.")
except Exception as e:
    print(f"\n[FAILURE] Unhandled exception during reconciliation: {e}")
    import traceback
    traceback.print_exc()

# Restore original method
client._request = real_request

print("\n================================================================================")
print("CLEANUP: FLATTENING TEST POSITION")
print("================================================================================")
try:
    flatten_res = client.place_order(
        symbol="ETHUSDT",
        side="SELL",
        order_type="MARKET",
        quantity=0.01,
        intent_id="test_flatten_after_timeout",
    )
    print(f"Flatten Order Status: {flatten_res.get('order', {}).get('status')}")
except Exception as e:
    print(f"Error flattening: {e}")

# Audit final balance
balances = client.get_account_balance()
for b in balances:
    if b.get("asset") == "USDT":
        print(f"Final USDT Balance: {b.get('balance')} (Available: {b.get('availableBalance')})")
print("================================================================================")
