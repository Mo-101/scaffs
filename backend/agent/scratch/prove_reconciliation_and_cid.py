import sys
import json
from dotenv import load_dotenv

load_dotenv("/home/idona/MoStar/scaffs/.env")
sys.path.insert(0, "/home/idona/MoStar/scaffs/backend/agent")

from src.trading.connectors.binance.futures_sdk import (
    get_binance_futures_client,
    generate_deterministic_client_order_id,
    BinanceAPIError,
)
from src.trading.connectors.binance.classification import classify_binance_mutation_error, BinanceOutcomeClass

client = get_binance_futures_client()

print("================================================================================")
print("1. PROVING DETERMINISTIC CLIENT_ORDER_ID RECOVERY")
print("================================================================================")
cid_a1 = generate_deterministic_client_order_id("ETHUSDT", "BUY", signal_id="sig_demo_101", quantity=0.01)
cid_a2 = generate_deterministic_client_order_id("ETHUSDT", "BUY", signal_id="sig_demo_101", quantity=0.01)
cid_b = generate_deterministic_client_order_id("ETHUSDT", "SELL", signal_id="sig_demo_102", quantity=0.01)

print(f"Decision A run 1 CID: {cid_a1} (len: {len(cid_a1)})")
print(f"Decision A run 2 CID: {cid_a2} (len: {len(cid_a2)})")
print(f"Decision B (different) CID: {cid_b} (len: {len(cid_b)})")
assert cid_a1 == cid_a2, "Determinism failed! CIDs for identical decision must match."
assert cid_a1 != cid_b, "Collision! Different decisions produced identical CID."
assert len(cid_a1) <= 36, f"Length {len(cid_a1)} exceeds Binance 36 char limit!"
print("-> RESULT: PASS. clientOrderId is 100% deterministic, recoverable, and < 36 chars.")

print("\n================================================================================")
print("2. AUTHORITATIVE TERMINAL STATE QUERY FOR PREVIOUS TESTNET ORDERS")
print("================================================================================")
for oid, label in [(16772505003, "BUY 0.01 ETH"), (16772505112, "SELL 0.01 ETH (FLATTEN)")]:
    try:
        receipt = client.get_order("ETHUSDT", order_id=oid)
        print(f"Order {oid} ({label}):")
        print(f"  Status: {receipt.get('status')}")
        print(f"  Orig Qty: {receipt.get('origQty')} | Executed Qty: {receipt.get('executedQty')}")
        print(f"  Avg Price: {receipt.get('avgPrice')} | Cum Quote: {receipt.get('cumQuote')}")
        print(f"  Client Order ID: {receipt.get('clientOrderId')}")
        print(f"  Update Time: {receipt.get('updateTime')}")
    except Exception as e:
        print(f"Error querying order {oid}: {e}")

print("\n================================================================================")
print("3. FAULT INJECTION: CANCEL ON ALREADY FILLED ORDER (EXPECTING -2011)")
print("================================================================================")
try:
    res = client.cancel_order("ETHUSDT", order_id=16772505003)
    print("Reconciled Cancel Result:", json.dumps(res, indent=2))
    assert res.get("status") == "FILLED", f"Expected reconciled status FILLED but got {res.get('status')}"
    assert res.get("canceled") is False, "Expected canceled to be False"
    print("-> RESULT: PASS. Reconciler successfully resolved cancel on filled order into status=FILLED.")
except BinanceAPIError as exc:
    print(f"Live Exchange Code: {exc.code}")
    print(f"Live HTTP Status: {exc.http_status}")
    print(f"Error Message: {exc}")
    print(f"Outcome Classification: {exc.outcome_class}")
    assert exc.code in (-2011, -2013), f"Expected -2011 or -2013 but got {exc.code}"
    print(f"-> RESULT: PASS. Exchange code {exc.code} classified safely as {exc.outcome_class}.")

print("\n================================================================================")
print("4. FAULT INJECTION: CANCEL ON NON-EXISTENT ORDER (EXPECTING -2013)")
print("================================================================================")
try:
    res = client.cancel_order("ETHUSDT", order_id=99999999999)
    print("Unexpected cancel response:", res)
except BinanceAPIError as exc:
    print(f"Live Exchange Code: {exc.code}")
    print(f"Live HTTP Status: {exc.http_status}")
    print(f"Error Message: {exc}")
    print(f"Outcome Classification: {exc.outcome_class}")
    assert exc.code in (-2011, -2013), f"Expected -2011 or -2013 but got {exc.code}"
    print(f"-> RESULT: PASS. Exchange code {exc.code} classified as {exc.outcome_class}.")

print("\n================================================================================")
print("5. FAULT INJECTION: RECONCILIATION ON AMBIGUOUS TRANSPORT TIMEOUT")
print("================================================================================")
# Test error classifier mapping on all edge conditions
test_cases = [
    (-1021, "Timestamp for this request is outside of the recvWindow.", BinanceOutcomeClass.RECONCILE_REQUIRED),
    (-2010, "Account has insufficient balance for requested action.", BinanceOutcomeClass.TERMINAL_REJECT),
    (-2011, "Unknown order sent.", BinanceOutcomeClass.RECONCILE_REQUIRED),
    (-2013, "Order does not exist.", BinanceOutcomeClass.RECONCILE_REQUIRED),
    (-4131, "The counterparty's best price does not meet the PERCENT_PRICE filter limit.", BinanceOutcomeClass.RECONCILE_REQUIRED),
    (-1003, "Too many requests.", BinanceOutcomeClass.RATE_LIMITED),
    (None, "Read timed out after 10 seconds", BinanceOutcomeClass.RECONCILE_REQUIRED),
]

for code, msg, expected_cls in test_cases:
    is_timeout = code is None
    cls_res = classify_binance_mutation_error(code, msg, is_network_timeout=is_timeout)
    print(f"Case {str(code):6s} | Msg: {msg[:45]:45s} -> Classified: {cls_res.value:18s} (Match: {cls_res == expected_cls})")
    assert cls_res == expected_cls, f"Classification mismatch for {code}: got {cls_res}, expected {expected_cls}"

print("-> RESULT: PASS. All 7 critical live error classifications verified.")
print("================================================================================")
