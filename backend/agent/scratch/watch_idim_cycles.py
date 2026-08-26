import time
import urllib.request
import json
import psycopg

print("================================================================================")
print("OBSERVING IDIM IKANG SCANNER LIVE TELEMETRY & PHASE 2 GATE DYNAMICS")
print("================================================================================")

# Query recent rows in financial.training_candidates
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*), max(ts) FROM financial.training_candidates;")
    total, max_ts = cur.fetchone()
    print(f"financial.training_candidates: Total={total}, Latest Timestamp={max_ts}")
    
    cur.execute("""
        SELECT symbol, side, score, rejection_gate, would_have_passed_live, regime, ts 
        FROM financial.training_candidates 
        ORDER BY ts DESC 
        LIMIT 10;
    """)
    print("\nLatest 10 candidates in financial.training_candidates:")
    for r in cur.fetchall():
        print(f"  {r[0]:10s} {r[1]:5s} | Score: {r[2]} | Gate: {str(r[3]):30s} | PassLive: {r[4]} | Regime: {r[5]}")

print("\n--------------------------------------------------------------------------------")
print("QUERYING IDIM IKANG API (/api/stats and /api/cell-performance):")
print("--------------------------------------------------------------------------------")
try:
    with urllib.request.urlopen("http://127.0.0.1:41050/api/stats") as resp:
        stats = json.loads(resp.read().decode())
        print("API /api/stats latest_cycle:")
        print(json.dumps(stats.get("latest_cycle", {}), indent=2))
        print(f"Unresolved signals in buffer: {stats.get('unresolved')}")
except Exception as e:
    print("Error querying /api/stats:", e)

try:
    with urllib.request.urlopen("http://127.0.0.1:41050/api/cell-performance") as resp:
        cells = json.loads(resp.read().decode())
        print(f"\nAPI /api/cell-performance summary: {len(cells)} cells active.")
except Exception as e:
    print("Error querying /api/cell-performance:", e)
print("================================================================================")
