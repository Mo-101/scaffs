import psycopg

print("=== DETAILED PROBE: paper_trading IN 'mostar' (PORT 5433) ===")
with psycopg.connect("dbname=mostar port=5433", connect_timeout=3) as conn, conn.cursor() as cur:
    print("\n1. paper_trading.trading_accounts:")
    cur.execute("SELECT * FROM paper_trading.trading_accounts LIMIT 10;")
    cols = [d[0] for d in cur.description]
    print("Columns:", cols)
    for r in cur.fetchall():
        print("  ", dict(zip(cols, r)))
        
    print("\n2. paper_trading.worker_heartbeats:")
    cur.execute("SELECT * FROM paper_trading.worker_heartbeats ORDER BY last_heartbeat DESC LIMIT 10;")
    cols = [d[0] for d in cur.description]
    print("Columns:", cols)
    for r in cur.fetchall():
        print("  ", dict(zip(cols, r)))
        
    print("\n3. paper_trading.paper_cycle_events latest:")
    cur.execute("SELECT count(*), min(cycle_completed_at), max(cycle_completed_at) FROM paper_trading.paper_cycle_events;")
    print("  Aggregates (count, min, max):", cur.fetchone())
    
    cur.execute("SELECT worker_id, count(*), max(cycle_completed_at) FROM paper_trading.paper_cycle_events GROUP BY worker_id ORDER BY worker_id;")
    print("  By worker_id:")
    for r in cur.fetchall():
        print("  ", r)
