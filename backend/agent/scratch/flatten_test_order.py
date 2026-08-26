import json
import urllib.request

print("================================================================================")
print("FLATTENING TEST POSITION (SELL 0.01 ETHUSDT)")
print("================================================================================")
req_data_sell = json.dumps({
    "symbol": "ETHUSDT",
    "side": "SELL",
    "quantity": 0.01,
    "order_type": "MARKET"
}).encode("utf-8")

req = urllib.request.Request(
    "http://localhost:3000/paper-sessions/binance-testnet/order",
    data=req_data_sell,
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode())
        print(f"Flatten Order Result:\n{json.dumps(body, indent=2)}")
except Exception as e:
    print(f"Error flattening: {e}")
