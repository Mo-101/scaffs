import psycopg

print("=== MIGRATING 'mostar' ON PORT 5433 ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("""
        ALTER TABLE paper_trading.paper_cycle_events 
        ADD COLUMN IF NOT EXISTS decision_funnel JSONB DEFAULT '{}'::jsonb;
    """)
    conn.commit()
    print("Successfully ensured 'decision_funnel' column exists on paper_trading.paper_cycle_events!")
    
    # Also check if paper_trading.trading_accounts has last_heartbeat
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_schema = 'paper_trading' AND table_name = 'trading_accounts' AND column_name = 'last_heartbeat';
    """)
    if not cur.fetchall():
        cur.execute("""
            ALTER TABLE paper_trading.trading_accounts 
            ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;
        """)
        # Populate last_heartbeat from updated_at or worker_heartbeats
        cur.execute("""
            UPDATE paper_trading.trading_accounts ta
            SET last_heartbeat = wh.last_seen_at
            FROM paper_trading.worker_heartbeats wh
            WHERE ta.account_id = wh.account_id;
        """)
        conn.commit()
        print("Successfully added and populated last_heartbeat on paper_trading.trading_accounts!")
    else:
        print("last_heartbeat column already present on paper_trading.trading_accounts.")
