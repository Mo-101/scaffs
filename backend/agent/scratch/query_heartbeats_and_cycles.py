import psycopg

with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'paper_trading' AND table_name = 'worker_heartbeats';")
    print("worker_heartbeats columns:", cur.fetchall())
    
    cur.execute("SELECT * FROM paper_trading.worker_heartbeats;")
    cols = [d[0] for d in cur.description]
    print("\nworker_heartbeats rows:")
    for r in cur.fetchall():
        print("  ", dict(zip(cols, r)))
        
    cur.execute("SELECT min(cycle_completed_at), max(cycle_completed_at), count(*) FROM paper_trading.paper_cycle_events;")
    print("\npaper_cycle_events summary (min, max, count):", cur.fetchone())
    
    cur.execute("SELECT worker_id, count(*), min(cycle_completed_at), max(cycle_completed_at) FROM paper_trading.paper_cycle_events GROUP BY worker_id ORDER BY worker_id;")
    print("\npaper_cycle_events by worker_id:")
    for r in cur.fetchall():
        print("  ", r)
