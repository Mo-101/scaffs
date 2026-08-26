import psycopg
import sys

print("=== PROBING LOCAL POSTGRESQL CLUSTER 16/main (PORT 5433) ===")
try:
    with psycopg.connect("dbname=postgres port=5433", connect_timeout=3) as conn, conn.cursor() as cur:
        cur.execute("SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database;")
        dbs = cur.fetchall()
        print("Databases present:")
        for db in dbs:
            print(f"  - {db[0]:20s}: {db[1]}")
except Exception as e:
    print(f"Failed to connect to postgres on 5433: {e}")

print("\n=== PROBING DATABASE 'idim_ikang' ON PORT 5433 ===")
try:
    with psycopg.connect("dbname=idim_ikang port=5433", connect_timeout=3) as conn, conn.cursor() as cur:
        cur.execute("SELECT schema_name FROM information_schema.schemata;")
        schemas = [s[0] for s in cur.fetchall()]
        print(f"Schemas: {schemas}")
        
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema');")
        tables = cur.fetchall()
        print(f"Tables ({len(tables)} found):")
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {t[0]}.{t[1]};")
            cnt = cur.fetchone()[0]
            print(f"  - {t[0]}.{t[1]}: {cnt} rows")
            
        if any(t[1] == 'accounts' for t in tables):
            cur.execute("SELECT account_id, worker_id, strategy_id, timeframe, leverage, last_heartbeat FROM accounts;")
            accounts = cur.fetchall()
            print(f"\nAccounts in accounts table ({len(accounts)}):")
            for a in accounts:
                print(f"  {a}")
                
        if any(t[1] == 'paper_cycle_events' for t in tables):
            cur.execute("SELECT count(*), max(cycle_completed_at) FROM paper_trading.paper_cycle_events;")
            pce = cur.fetchone()
            print(f"\npaper_trading.paper_cycle_events: count={pce[0]}, max(cycle_completed_at)={pce[1]}")
except Exception as e:
    print(f"Failed to query idim_ikang on 5433: {e}")
