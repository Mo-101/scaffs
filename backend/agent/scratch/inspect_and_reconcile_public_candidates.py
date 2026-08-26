import psycopg

print("=== INSPECTING ROWS IN public.training_candidates ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM public.training_candidates;")
    count = cur.fetchone()[0]
    print(f"Total rows in public.training_candidates: {count}")
    
    if count > 0:
        cur.execute("SELECT min(ts), max(ts), count(*) FROM public.training_candidates;")
        print("Timestamp range:", cur.fetchone())
        
        cur.execute("SELECT symbol, side, count(*) FROM public.training_candidates GROUP BY symbol, side ORDER BY count(*) DESC LIMIT 10;")
        print("Sample distribution:")
        for r in cur.fetchall():
            print("  ", r)
            
    cur.execute("SELECT count(*) FROM financial.training_candidates;")
    fin_count = cur.fetchone()[0]
    print(f"\nTotal rows in financial.training_candidates: {fin_count}")
