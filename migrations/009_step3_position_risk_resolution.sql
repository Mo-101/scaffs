-- Step 3 Position Risk Resolution: idempotent close reservations, quarantine, and closed-position ledger.

CREATE TABLE IF NOT EXISTS paper_trading.close_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_order_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity NUMERIC(36, 18) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'PENDING',
    binance_order_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_close_reservations_symbol_status
    ON paper_trading.close_reservations(symbol, status);

CREATE TABLE IF NOT EXISTS paper_trading.quarantine (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    binance_quantity NUMERIC(36, 18) NOT NULL,
    scaffs_quantity NUMERIC(36, 18) NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL,
    reason TEXT,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_quarantine_symbol_resolved
    ON paper_trading.quarantine(symbol, resolved_at);

CREATE TABLE IF NOT EXISTS paper_trading.closed_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price NUMERIC(36, 18),
    exit_price NUMERIC(36, 18),
    quantity NUMERIC(36, 18) NOT NULL,
    realized_pnl NUMERIC(28, 10),
    commission NUMERIC(28, 10),
    closed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_closed_positions_symbol_closed
    ON paper_trading.closed_positions(symbol, closed_at);
