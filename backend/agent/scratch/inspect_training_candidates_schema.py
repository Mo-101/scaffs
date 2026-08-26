import psycopg

print("=== CHECKING PUBLIC VS FINANCIAL TRAINING_CANDIDATES ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    for schema in ['public', 'financial']:
        cur.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = '{schema}' AND table_name = 'training_candidates';
        """)
        cols = [c[0] for c in cur.fetchall()]
        print(f"\nSchema '{schema}'.training_candidates: ({len(cols)} columns)")
        print("  Cols:", cols)
        print("  Has 'trace_data':", 'trace_data' in cols)
