import json
import urllib.request
import urllib.error

print("================================================================================")
print("TEST 1: HARD SAFETY CAP REJECTION (ETHUSDT qty=0.06 -> ~$148 USD > $100 USD)")
print("================================================================================")
req_data_oversized = json.dumps({
    "symbol": "ETHUSDT",
    "side": "BUY",
    "quantity": 0.06,
    "order_type": "MARKET"
}).encode("utf-8")

req_1 = urllib.request.Request(
    "http://localhost:3000/paper-sessions/binance-testnet/order",
    data=req_data_oversized,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req_1) as resp:
        print("UNEXPECTED SUCCESS (Should have failed):", resp.status, resp.read().decode())
except urllib.error.HTTPError as err:
    print(f"HTTP Status: {err.code}")
    print(f"Response Body: {err.read().decode()}")

print("\n================================================================================")
print("TEST 2: MANUAL VALID TEST ORDER (ETHUSDT qty=0.01 -> ~$24.75 USDT, >$20 MIN & <$100 MAX)")
print("================================================================================")
req_data_valid = json.dumps({
    "symbol": "ETHUSDT",
    "side": "BUY",
    "quantity": 0.01,
    "order_type": "MARKET"
}).encode("utf-8")

req_2 = urllib.request.Request(
    "http://localhost:3000/paper-sessions/binance-testnet/order",
    data=req_data_valid,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req_2) as resp:
        print(f"HTTP Status: {resp.status}")
        body = resp.read().decode()
        parsed = json.loads(body)
        print(f"Order Result:\n{json.dumps(parsed, indent=2)}")
except urllib.error.HTTPError as err:
    print(f"HTTP Error {err.code}: {err.read().decode()}")
except Exception as e:
    print(f"Error: {e}")

print("\n================================================================================")
print("TEST 3: POST-TRADE ACCOUNT BALANCE & POSITIONS")
print("================================================================================")
try:
    with urllib.request.urlopen("http://localhost:3000/paper-sessions/binance-testnet/status") as resp:
        body = json.loads(resp.read().decode())
        print("Binance Testnet Status:")
        print(f"  USDT Balance: {body.get('usdt_balance')}")
        print(f"  Latency: {body.get('latency_ms')} ms")
        print(f"  Host: {body.get('host')}")
except Exception as e:
    print(f"Error fetching status: {e}")
print("================================================================================")
