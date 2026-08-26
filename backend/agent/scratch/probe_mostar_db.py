import psycopg

print("=== PROBING DATABASE 'mostar' ON PORT 5433 ===")
try:
    with psycopg.connect("dbname=mostar port=5433", connect_timeout=3) as conn, conn.cursor() as cur:
        cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('pg_catalog', 'information_schema');")
        schemas = [s[0] for s in cur.fetchall()]
        print(f"Schemas: {schemas}")
        
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema');")
        tables = cur.fetchall()
        print(f"\nTables found in 'mostar' ({len(tables)} tables):")
        for t in tables:
            try:
                cur.execute(f"SELECT count(*) FROM {t[0]}.{t[1]};")
                cnt = cur.fetchone()[0]
                print(f"  - {t[0]}.{t[1]}: {cnt} rows")
            except Exception as ce:
                print(f"  - {t[0]}.{t[1]}: (error: {ce})")
                
        # Check accounts
        try:
            cur.execute("SELECT account_id, worker_id, strategy_id, timeframe, leverage, last_heartbeat FROM accounts;")
            accounts = cur.fetchall()
            print(f"\nAccounts in 'mostar.accounts' ({len(accounts)}):")
            for a in accounts:
                print(f"  {a}")
        except Exception as ae:
            print(f"Accounts query note: {ae}")
            
        # Check paper_trading.paper_cycle_events
        try:
            cur.execute("SELECT count(*), max(cycle_completed_at) FROM paper_trading.paper_cycle_events;")
            pce = cur.fetchone()
            print(f"\npaper_trading.paper_cycle_events: count={pce[0]}, max(cycle_completed_at)={pce[1]}")
        except Exception as pe:
            print(f"paper_cycle_events note: {pe}")
except Exception as e:
    print(f"Failed to query mostar on 5433: {e}")
