-- Signal Queue: atomic claim/dispatch idempotency, upstream signal provenance,
-- and a batch-independent absolute quality score.

ALTER TABLE paper_trading.signal_queue
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS claim_token TEXT,
    ADD COLUMN IF NOT EXISTS signal_generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS absolute_quality_score NUMERIC;

-- True exactly-once-in-flight semantics per upstream signal id: only one
-- ACTIVE (PENDING or CLAIMED) row may exist for a given source_signal_id at
-- a time. Terminal rows are excluded so the same source_signal_id may be
-- legitimately re-ingested later (e.g. after TTL expiry or a transient
-- collision/leverage/margin failure) -- see idim_feed_bridge.py's
-- retry-eligible status list, which must stay a SUBSET of "not PENDING/CLAIMED"
-- here.
CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_queue_active_source_signal_id
    ON paper_trading.signal_queue (source_signal_id)
    WHERE source_signal_id IS NOT NULL AND status IN ('PENDING', 'CLAIMED');

CREATE INDEX IF NOT EXISTS idx_signal_queue_claimed_at
    ON paper_trading.signal_queue (claimed_at)
    WHERE status = 'CLAIMED';
