import psycopg

print("=== SCHEMA PROBE: paper_trading.paper_cycle_events IN 'mostar' ===")
with psycopg.connect("dbname=mostar port=5433", connect_timeout=3) as conn, conn.cursor() as cur:
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = 'paper_trading' AND table_name = 'paper_cycle_events';
    """)
    cols = cur.fetchall()
    print("Columns in paper_trading.paper_cycle_events:")
    for col in cols:
        print(f"  - {col[0]:30s}: {col[1]}")
        
    cur.execute("SELECT * FROM paper_trading.paper_cycle_events ORDER BY cycle_completed_at DESC LIMIT 3;")
    col_names = [d[0] for d in cur.description]
    print("\nSample rows:")
    for r in cur.fetchall():
        print("  ", dict(zip(col_names, r)))
