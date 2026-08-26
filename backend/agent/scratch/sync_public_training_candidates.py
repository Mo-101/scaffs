import psycopg

print("=== ENSURING MISSING COLUMNS EXIST ON public.training_candidates ===")
with psycopg.connect("dbname=mostar port=5433") as conn, conn.cursor() as cur:
    cur.execute("""
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS trace_data JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS family_indicators JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS directional_long_score NUMERIC;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS directional_short_score NUMERIC;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS directional_net NUMERIC;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS directional_margin NUMERIC;
        ALTER TABLE public.training_candidates ADD COLUMN IF NOT EXISTS directional_primary_side TEXT;
    """)
    conn.commit()
    print("Successfully synchronized public.training_candidates columns!")
