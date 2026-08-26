import urllib.request
import json

BASE_URL = "http://127.0.0.1:3000/paper-sessions/signal-queue"

def test_api():
    print("=== 1. TESTING ENQUEUE WITH LOW SCORE (EXPECTING QUALITY GATE REJECT) ===")
    req = urllib.request.Request(
        f"{BASE_URL}/enqueue",
        data=json.dumps({"symbol": "BTCUSDT", "side": "BUY", "raw_score": 52.0}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        print("ERROR: Should have failed quality gate!")
    except urllib.error.HTTPError as e:
        print(f"Passed Hard Gate Rejection Test: HTTP {e.code} - {e.read().decode()}")

    print("\n=== 2. TESTING ENQUEUE WITH HIGH CONVICTION SIGNAL ===")
    req2 = urllib.request.Request(
        f"{BASE_URL}/enqueue",
        data=json.dumps({
            "symbol": "ETHUSDT",
            "side": "BUY",
            "producer": "idim_ikang",
            "raw_score": 82.5,
            "timeframe": "15m",
            "criteria_vector": {"regime": "STRONG_UPTREND", "adx14": 32.0, "vol_ratio": 1.4},
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req2) as resp:
        enqueue_res = json.loads(resp.read().decode())
        print("Enqueue result:", json.dumps(enqueue_res, indent=2))
        queue_id = enqueue_res.get("id")

    print("\n=== 3. QUERYING TOPSIS-RANKED PENDING QUEUE ===")
    with urllib.request.urlopen(f"{BASE_URL}/pending") as resp:
        pending_res = json.loads(resp.read().decode())
        print(f"Pending signals count: {pending_res.get('count')}")
        for s in pending_res.get("signals", [])[:3]:
            print(f"  [{s['id'][:8]}] {s['symbol']} {s['side']} | RawScore: {s['raw_score']} | TOPSIS: {s.get('topsis_score')} | Target: {s['target_strategy']}")

    print("\n=== 4. QUERYING QUEUE HISTORY ===")
    with urllib.request.urlopen(f"{BASE_URL}/history?limit=5") as resp:
        hist = json.loads(resp.read().decode())
        print(f"History count: {hist.get('count')}")
        for h in hist.get("history", [])[:3]:
            print(f"  [{h['id'][:8]}] {h['symbol']} {h['side']} -> Status: {h['status']} | Strategy: {h['target_strategy']}")

if __name__ == "__main__":
    test_api()
