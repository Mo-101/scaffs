import urllib.request
import json

print("================================================================================")
print("MAKING THE RIVER OF FIRE FLOW: SYNCING IDIM IKANG INTO SCAFFS SIGNAL QUEUE")
print("================================================================================")

req = urllib.request.Request(
    "http://127.0.0.1:3000/paper-sessions/signal-queue/sync-idim",
    data=json.dumps({"auto_dispatch": False}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req) as resp:
    sync_res = json.loads(resp.read().decode())
    print("Sync Result:")
    print(json.dumps(sync_res, indent=2))

print("\n--------------------------------------------------------------------------------")
print("QUERYING TOPSIS-RANKED PENDING QUEUE AFTER IDIM SYNC:")
print("--------------------------------------------------------------------------------")

with urllib.request.urlopen("http://127.0.0.1:3000/paper-sessions/signal-queue/pending?limit=10") as resp:
    pending = json.loads(resp.read().decode())
    print(f"Total Pending Signals: {pending.get('count')}")
    for s in pending.get("signals", []):
        print(f"  [{s['id'][:8]}] {s['symbol']:10s} {s['side']:5s} | RawScore: {s['raw_score']:5.1f} | TOPSIS: {s.get('topsis_score'):.4f} | Target: {s['target_strategy']}")

print("================================================================================")
