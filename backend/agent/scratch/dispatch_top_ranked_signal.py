import urllib.request
import json

print("================================================================================")
print("DISPATCHING TOP RANKED SIGNAL FROM IDIM IKANG TO BINANCE FUTURES TESTNET")
print("================================================================================")

# 1. Fetch pending
with urllib.request.urlopen("http://127.0.0.1:3000/paper-sessions/signal-queue/pending?limit=1") as resp:
    data = json.loads(resp.read().decode())
    top_signal = data["signals"][0]
    print(f"Top Signal selected for execution: [{top_signal['id']}] {top_signal['symbol']} {top_signal['side']} (Score: {top_signal['raw_score']}, TOPSIS: {top_signal['topsis_score']})")

# 2. Dispatch
dispatch_req = urllib.request.Request(
    "http://127.0.0.1:3000/paper-sessions/signal-queue/dispatch",
    data=json.dumps({
        "queue_id": top_signal["id"],
        "notional_usd": 25.0,
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(dispatch_req) as resp:
    dispatch_res = json.loads(resp.read().decode())
    print("\nLive Dispatch Result:")
    print(json.dumps(dispatch_res, indent=2))

print("================================================================================")
