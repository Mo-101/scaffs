-- Migration: 009b_signal_queue_base.sql
-- Description: Create paper_trading.signal_queue table, live_fills, and strategy_actually_run column

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
    completed_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    claim_token TEXT,
    signal_generated_at TIMESTAMPTZ,
    absolute_quality_score NUMERIC,
    requested_quantity NUMERIC,
    filled_quantity NUMERIC,
    entry_ttl_seconds INTEGER DEFAULT 900
);

CREATE INDEX IF NOT EXISTS idx_signal_queue_status_created ON paper_trading.signal_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_signal_queue_symbol_status ON paper_trading.signal_queue (symbol, status);
CREATE INDEX IF NOT EXISTS idx_signal_queue_target_strategy ON paper_trading.signal_queue (target_strategy, status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_queue_active_source_signal_id
    ON paper_trading.signal_queue (source_signal_id)
    WHERE source_signal_id IS NOT NULL
      AND status IN ('PENDING', 'CLAIMED', 'DISPATCHED', 'PARTIALLY_FILLED');

CREATE INDEX IF NOT EXISTS idx_signal_queue_claimed_at
    ON paper_trading.signal_queue (claimed_at) WHERE status = 'CLAIMED';

CREATE INDEX IF NOT EXISTS idx_signal_queue_pending_entry
    ON paper_trading.signal_queue (status, dispatched_at)
    WHERE status IN ('DISPATCHED', 'PARTIALLY_FILLED', 'PROTECTION_FAILED');

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
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (exchange_order_id, exchange_fill_id)
);

CREATE INDEX IF NOT EXISTS idx_live_fills_symbol_side ON paper_trading.live_fills (symbol, side);

-- Add strategy_actually_run column to paper_trading.trading_accounts and equity_history
ALTER TABLE paper_trading.trading_accounts ADD COLUMN IF NOT EXISTS strategy_actually_run TEXT;
ALTER TABLE paper_trading.equity_history ADD COLUMN IF NOT EXISTS strategy_actually_run TEXT;
