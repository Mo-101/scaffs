import psycopg

print("=== CREATING paper_trading.signal_queue IN DATABASE 'mostar' ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_trading.signal_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_signal_id TEXT,
            producer TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            raw_score NUMERIC,
            criteria_vector JSONB DEFAULT '{}'::jsonb,
            topsis_score NUMERIC,
            target_strategy TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            rejection_reason TEXT,
            execution_order_id TEXT,
            execution_client_order_id TEXT,
            ttl_seconds INTEGER DEFAULT 300,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            dispatched_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_signal_queue_status_created ON paper_trading.signal_queue (status, created_at);
        CREATE INDEX IF NOT EXISTS idx_signal_queue_symbol_status ON paper_trading.signal_queue (symbol, status);
        CREATE INDEX IF NOT EXISTS idx_signal_queue_target_strategy ON paper_trading.signal_queue (target_strategy, status);
    """)
    conn.commit()
    print("Successfully created paper_trading.signal_queue with indexes!")
    
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'paper_trading' AND table_name = 'signal_queue';")
    for col in cur.fetchall():
        print(f"  - {col[0]:25s}: {col[1]}")
