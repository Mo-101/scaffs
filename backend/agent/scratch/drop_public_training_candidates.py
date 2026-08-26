import psycopg

print("=== DROPPING EMPTY SHADOW TABLE public.training_candidates ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM public.training_candidates;")
    cnt = cur.fetchone()[0]
    print(f"Current rows in public.training_candidates: {cnt}")
    if cnt == 0:
        cur.execute("DROP TABLE public.training_candidates;")
        conn.commit()
        print("Successfully dropped public.training_candidates (0 rows). Only financial.training_candidates remains!")
    else:
        print("Table is not empty, skipping drop.")
        
    cur.execute("SELECT count(*) FROM financial.training_candidates;")
    print("financial.training_candidates total rows:", cur.fetchone()[0])
