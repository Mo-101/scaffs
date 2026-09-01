-- Phase 2: Empirical Data Accumulation & Multi-Leg Shadow Analytics
-- Depends on: 001_hybrid_phase1.sql
BEGIN;

-- ============================================================================
-- A. OBSERVATION SOURCE TAGGING
-- ============================================================================

-- Add observation_source to signal_proposals (explicit, CHECK-enforced)
ALTER TABLE financial.signal_proposals
  ADD COLUMN IF NOT EXISTS observation_source text
  NOT NULL DEFAULT 'LIVE_SHADOW'
  CHECK (observation_source IN ('LIVE_SHADOW','ACCEPTANCE_TEST','BACKFILL','SYNTHETIC'));

-- Add observation_source to shadow_engine_performance
ALTER TABLE financial.shadow_engine_performance
  ADD COLUMN IF NOT EXISTS observation_source text
  NOT NULL DEFAULT 'LIVE_SHADOW'
  CHECK (observation_source IN ('LIVE_SHADOW','ACCEPTANCE_TEST','BACKFILL','SYNTHETIC'));

-- Retroactively tag acceptance-test rows inserted during Phase 1 verification.
-- These are the deliberate test fixtures with exactly R=2.5, MFE=2.7, MAE=0.2, +$50.
UPDATE financial.shadow_engine_performance
  SET observation_source = 'ACCEPTANCE_TEST'
  WHERE status = 'CLOSED'
    AND r_multiple = 2.5
    AND mfe_r = 2.7
    AND mae_r = 0.2;

-- Tag matching proposals
UPDATE financial.signal_proposals sp
  SET observation_source = 'ACCEPTANCE_TEST'
  FROM financial.shadow_engine_performance sep
  WHERE sp.proposal_id = sep.proposal_id
    AND sep.observation_source = 'ACCEPTANCE_TEST';

-- ============================================================================
-- B. SHADOW POSITION HOLDING PERIOD SEPARATION
-- ============================================================================

-- valid_until = "too stale to ENTER" (already exists)
-- max_hold_until = "close position if still open at this time" (new)
ALTER TABLE financial.shadow_engine_performance
  ADD COLUMN IF NOT EXISTS max_hold_until timestamptz,
  ADD COLUMN IF NOT EXISTS exit_policy_version text DEFAULT 'v1_tp_sl_time',
  ADD COLUMN IF NOT EXISTS exit_reason text CHECK (exit_reason IS NULL OR exit_reason IN (
      'TP','SL','TIME','LIQUIDATION','FUNDING_EXIT',
      'GRID_COMPLETE','ARBITRAGE_CLOSE','INVALIDATED'
  )),
  ADD COLUMN IF NOT EXISTS leg_count smallint DEFAULT 1;

-- ============================================================================
-- C. MULTI-LEG PROPOSAL MODEL
-- ============================================================================

CREATE TABLE IF NOT EXISTS financial.proposal_legs (
    leg_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_id     uuid NOT NULL REFERENCES financial.signal_proposals(proposal_id) ON DELETE CASCADE,
    leg_index       smallint NOT NULL DEFAULT 0,
    leg_role        text NOT NULL DEFAULT 'ENTRY' CHECK (leg_role IN (
        'ENTRY','HEDGE','GRID_LEVEL','FUNDING_LEG','EXIT',
        'SPOT_HEDGE','PERP_FUNDING_LEG'
    )),
    venue           text NOT NULL DEFAULT 'binance_futures',
    instrument      text NOT NULL,
    side            text NOT NULL CHECK (side IN ('BUY','SELL')),
    entry_price     double precision,
    quantity        double precision,
    notional_usd    double precision,
    fee_model       text DEFAULT 'maker_taker',
    funding_model   text,
    status          text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED','CANCELLED')),
    exit_price      double precision,
    exit_reason     text CHECK (exit_reason IS NULL OR exit_reason IN (
        'TP','SL','TIME','LIQUIDATION','FUNDING_EXIT',
        'GRID_COMPLETE','ARBITRAGE_CLOSE','INVALIDATED'
    )),
    fees_usd        double precision DEFAULT 0.0,
    funding_usd     double precision DEFAULT 0.0,
    net_pnl_usd     double precision,
    opened_at       timestamptz DEFAULT now(),
    closed_at       timestamptz,
    UNIQUE (proposal_id, leg_index)
);

CREATE INDEX IF NOT EXISTS idx_proposal_legs_proposal
    ON financial.proposal_legs(proposal_id);
CREATE INDEX IF NOT EXISTS idx_proposal_legs_open
    ON financial.proposal_legs(status) WHERE status = 'OPEN';

-- ============================================================================
-- D. GRID CAMPAIGN DERIVED NET POSITION VIEW
-- ============================================================================

CREATE OR REPLACE VIEW financial.grid_campaign_summary AS
SELECT
    pl.proposal_id,
    sp.producer,
    sp.strategy_version,
    sp.symbol,
    sp.regime,
    count(*) AS total_legs,
    count(*) FILTER (WHERE pl.side = 'BUY') AS buy_legs,
    count(*) FILTER (WHERE pl.side = 'SELL') AS sell_legs,
    -- Net inventory: positive = net long, negative = net short
    COALESCE(sum(CASE WHEN pl.side = 'BUY' THEN pl.quantity ELSE -pl.quantity END), 0) AS net_quantity,
    -- Inventory VWAP (buy side)
    CASE WHEN sum(pl.quantity) FILTER (WHERE pl.side = 'BUY') > 0
         THEN sum(pl.entry_price * pl.quantity) FILTER (WHERE pl.side = 'BUY')
              / sum(pl.quantity) FILTER (WHERE pl.side = 'BUY')
         ELSE NULL END AS buy_vwap,
    -- Inventory VWAP (sell side)
    CASE WHEN sum(pl.quantity) FILTER (WHERE pl.side = 'SELL') > 0
         THEN sum(pl.entry_price * pl.quantity) FILTER (WHERE pl.side = 'SELL')
              / sum(pl.quantity) FILTER (WHERE pl.side = 'SELL')
         ELSE NULL END AS sell_vwap,
    -- Realized PnL from closed legs
    sum(pl.net_pnl_usd) FILTER (WHERE pl.status = 'CLOSED') AS realized_pnl_usd,
    -- Total fees
    sum(pl.fees_usd) AS total_fees_usd,
    -- Total funding
    sum(pl.funding_usd) AS total_funding_usd,
    -- Max inventory (peak absolute quantity held)
    max(abs(pl.quantity)) AS max_single_leg_qty,
    -- Campaign status
    CASE WHEN count(*) FILTER (WHERE pl.status = 'OPEN') = 0 THEN 'COMPLETED'
         ELSE 'ACTIVE' END AS campaign_status,
    min(pl.opened_at) AS campaign_started_at,
    max(pl.closed_at) AS campaign_ended_at
FROM financial.proposal_legs pl
JOIN financial.signal_proposals sp USING (proposal_id)
WHERE sp.strategy_family = 'mean_reversion'
GROUP BY pl.proposal_id, sp.producer, sp.strategy_version, sp.symbol, sp.regime;

-- ============================================================================
-- E. MARK TICKS TABLE (symbol-deduplicated, NOT per-proposal)
-- ============================================================================

CREATE TABLE IF NOT EXISTS financial.mark_ticks (
    id                  bigserial PRIMARY KEY,
    symbol              text NOT NULL,
    mark_price          double precision NOT NULL,
    mark_source         text NOT NULL CHECK (mark_source IN ('WS_STREAM','REST_POLL','MANUAL')),
    exchange_event_ts   timestamptz,
    received_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mark_ticks_symbol_ts
    ON financial.mark_ticks (symbol, received_at DESC);

-- Permanent landmark marks (entry, exit, MFE, MAE, TP/SL crossing, funding events)
CREATE TABLE IF NOT EXISTS financial.mark_ticks_permanent (
    id                  bigserial PRIMARY KEY,
    proposal_id         uuid NOT NULL REFERENCES financial.signal_proposals(proposal_id) ON DELETE CASCADE,
    leg_id              uuid REFERENCES financial.proposal_legs(leg_id) ON DELETE SET NULL,
    symbol              text NOT NULL,
    mark_price          double precision NOT NULL,
    mark_source         text NOT NULL CHECK (mark_source IN ('WS_STREAM','REST_POLL','MANUAL')),
    mark_type           text NOT NULL CHECK (mark_type IN (
        'ENTRY','EXIT','MFE','MAE','TP_CROSSING','SL_CROSSING',
        'FUNDING_EVENT','MAX_HOLD_EXPIRY'
    )),
    exchange_event_ts   timestamptz,
    received_at         timestamptz NOT NULL DEFAULT now(),
    metadata            jsonb DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_mark_permanent_proposal
    ON financial.mark_ticks_permanent (proposal_id, received_at DESC);

-- ============================================================================
-- F. ENGINE HEARTBEAT / RUNTIME STATUS TELEMETRY
-- ============================================================================

CREATE TABLE IF NOT EXISTS financial.engine_runtime_status (
    engine              text PRIMARY KEY,
    last_scan_at        timestamptz,
    last_success_at     timestamptz,
    last_candidate_at   timestamptz,
    last_proposal_at    timestamptz,
    scans_completed     bigint NOT NULL DEFAULT 0,
    candidates_seen     bigint NOT NULL DEFAULT 0,
    proposals_emitted   bigint NOT NULL DEFAULT 0,
    proposals_rejected  bigint NOT NULL DEFAULT 0,
    last_rejection_reason text,
    last_error          text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Seed all 4 engines
INSERT INTO financial.engine_runtime_status (engine)
VALUES ('idim_ikang'), ('scaffs_picker'), ('grid_v3'), ('morning_glory')
ON CONFLICT (engine) DO NOTHING;

-- ============================================================================
-- G. UPDATED SCOREBOARD VIEW (LIVE_SHADOW only, extended stats)
-- ============================================================================

CREATE OR REPLACE VIEW financial.shadow_engine_scoreboard AS
SELECT
    p.producer,
    p.strategy_family,
    p.strategy_version,
    COALESCE(p.regime, 'UNKNOWN') AS regime,
    count(*) FILTER (WHERE s.status = 'CLOSED') AS closed_n,
    -- Expectancy: mean R-multiple
    avg(s.r_multiple) FILTER (WHERE s.status = 'CLOSED') AS expectancy_r,
    -- Median R
    percentile_cont(0.5) WITHIN GROUP (ORDER BY s.r_multiple)
        FILTER (WHERE s.status = 'CLOSED') AS median_r,
    -- R standard deviation
    stddev_samp(s.r_multiple) FILTER (WHERE s.status = 'CLOSED') AS r_stddev,
    -- 95% CI lower bound
    avg(s.r_multiple) FILTER (WHERE s.status = 'CLOSED')
      - 1.96 * COALESCE(stddev_samp(s.r_multiple) FILTER (WHERE s.status = 'CLOSED'), 0)
            / GREATEST(sqrt(count(*) FILTER (WHERE s.status = 'CLOSED')), 1) AS ci95_lower,
    -- 95% CI upper bound
    avg(s.r_multiple) FILTER (WHERE s.status = 'CLOSED')
      + 1.96 * COALESCE(stddev_samp(s.r_multiple) FILTER (WHERE s.status = 'CLOSED'), 0)
            / GREATEST(sqrt(count(*) FILTER (WHERE s.status = 'CLOSED')), 1) AS ci95_upper,
    -- Win rate
    avg((s.outcome = 'WIN')::int) FILTER (WHERE s.status = 'CLOSED') AS win_rate,
    -- Profit Factor = sum(wins) / abs(sum(losses))
    CASE WHEN sum(s.net_pnl_usd) FILTER (WHERE s.status = 'CLOSED' AND s.outcome = 'LOSS') < 0
         THEN sum(s.net_pnl_usd) FILTER (WHERE s.status = 'CLOSED' AND s.outcome = 'WIN')
            / abs(sum(s.net_pnl_usd) FILTER (WHERE s.status = 'CLOSED' AND s.outcome = 'LOSS'))
         ELSE NULL END AS profit_factor,
    -- MFE / MAE
    avg(s.mfe_r) FILTER (WHERE s.status = 'CLOSED') AS avg_mfe_r,
    avg(s.mae_r) FILTER (WHERE s.status = 'CLOSED') AS avg_mae_r,
    -- Net PnL
    sum(s.net_pnl_usd) FILTER (WHERE s.status = 'CLOSED') AS net_pnl_usd,
    -- Max drawdown (worst single-trade R)
    min(s.r_multiple) FILTER (WHERE s.status = 'CLOSED') AS max_drawdown_r,
    -- Avg time-in-market (seconds)
    avg(EXTRACT(EPOCH FROM (s.closed_at - s.opened_at)))
        FILTER (WHERE s.status = 'CLOSED') AS avg_time_in_market_s
FROM financial.signal_proposals p
JOIN financial.shadow_engine_performance s USING (proposal_id)
WHERE p.observation_source = 'LIVE_SHADOW'
GROUP BY 1,2,3,4;

-- ============================================================================
-- H. ENGINE DIRECTION AGREEMENT VIEW
-- ============================================================================

CREATE OR REPLACE VIEW financial.engine_direction_agreement AS
WITH pairs AS (
    SELECT
        a.producer AS engine_a,
        b.producer AS engine_b,
        a.symbol,
        a.side AS side_a,
        b.side AS side_b,
        (a.side = b.side) AS same_direction,
        a.generated_at
    FROM financial.signal_proposals a
    JOIN financial.signal_proposals b
        ON a.symbol = b.symbol
        AND a.producer < b.producer
        AND abs(EXTRACT(EPOCH FROM (a.generated_at - b.generated_at))) < 3600
    WHERE a.observation_source = 'LIVE_SHADOW'
      AND b.observation_source = 'LIVE_SHADOW'
)
SELECT
    engine_a,
    engine_b,
    count(*) AS overlap_n,
    avg(same_direction::int) AS same_direction_pct,
    1.0 - avg(same_direction::int) AS opposite_direction_pct
FROM pairs
GROUP BY 1, 2;

COMMIT;
