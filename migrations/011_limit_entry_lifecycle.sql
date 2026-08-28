-- LIMIT-entry-first order lifecycle: track requested vs. filled quantity,
-- the entry order's own cancel-on-TTL deadline (distinct from ttl_seconds,
-- which only gates PENDING/CLAIMED claim-eligibility), the new intermediate/
-- terminal statuses this introduces, and a live-fill provenance table.

ALTER TABLE paper_trading.signal_queue
    ADD COLUMN IF NOT EXISTS requested_quantity NUMERIC,
    ADD COLUMN IF NOT EXISTS filled_quantity NUMERIC,
    ADD COLUMN IF NOT EXISTS entry_ttl_seconds INTEGER DEFAULT 900;

-- Widen active-source-signal dedup: a resting entry or partial fill is still
-- live exposure, must still block a duplicate re-ingest at the DB level.
DROP INDEX IF EXISTS paper_trading.ux_signal_queue_active_source_signal_id;
CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_queue_active_source_signal_id
    ON paper_trading.signal_queue (source_signal_id)
    WHERE source_signal_id IS NOT NULL
      AND status IN ('PENDING', 'CLAIMED', 'DISPATCHED', 'PARTIALLY_FILLED');

-- Poller discovery index: "which rows need a fill/TTL check right now".
CREATE INDEX IF NOT EXISTS idx_signal_queue_pending_entry
    ON paper_trading.signal_queue (status, dispatched_at)
    WHERE status IN ('DISPATCHED', 'PARTIALLY_FILLED', 'PROTECTION_FAILED');

-- Live-fill provenance, kept SEPARATE from paper_trading.fills (whose
-- account_id FK requires a mode='paper' trading_account -- a real live fill
-- doesn't belong there and would corrupt that account's own bookkeeping).
-- Read by position/provenance.py::aggregate_fills() alongside
-- paper_trading.fills so PositionReconciler can see real live positions
-- instead of quarantining everything (it previously had no fill rows to
-- match against for live-testnet trades at all).
CREATE TABLE IF NOT EXISTS paper_trading.live_fills (
    fill_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_id UUID REFERENCES paper_trading.signal_queue(id),
    exchange_fill_id TEXT,
    exchange_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(36, 18) NOT NULL CHECK (quantity > 0),
    price NUMERIC(36, 18) NOT NULL CHECK (price > 0),
    fee NUMERIC(28, 10) NOT NULL DEFAULT 0,
    filled_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exchange_order_id, exchange_fill_id)
);

CREATE INDEX IF NOT EXISTS idx_live_fills_symbol_side
    ON paper_trading.live_fills (symbol, side);
