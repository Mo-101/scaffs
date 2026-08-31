BEGIN;

CREATE SCHEMA IF NOT EXISTS financial;

CREATE TABLE IF NOT EXISTS financial.signal_proposals (
    proposal_id             uuid PRIMARY KEY,
    idempotency_key         text NOT NULL UNIQUE,
    producer                text NOT NULL,
    strategy_family         text NOT NULL CHECK (
        strategy_family IN ('directional','momentum','mean_reversion','funding_arbitrage')
    ),
    strategy_version        text NOT NULL,
    git_sha                 text NOT NULL,
    symbol                  text NOT NULL,
    side                    text NOT NULL CHECK (side IN ('BUY','SELL')),
    generated_at            timestamptz NOT NULL,
    valid_until             timestamptz NOT NULL,
    raw_score               double precision,
    expected_r              double precision,
    expected_r_lower        double precision,
    expected_r_upper        double precision,
    reliability             double precision CHECK (reliability IS NULL OR reliability BETWEEN 0 AND 1),
    empirical_sample_n      integer NOT NULL DEFAULT 0 CHECK (empirical_sample_n >= 0),
    stop_distance_pct       double precision,
    target_distance_pct     double precision,
    regime                  text,
    freshness_seconds       double precision CHECK (freshness_seconds IS NULL OR freshness_seconds >= 0),
    context_snapshot_id     text,
    correlation_group       text,
    shadow_only             boolean NOT NULL DEFAULT true,
    native_payload          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now(),
    last_seen_at            timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_until > generated_at),
    CHECK (
        expected_r_lower IS NULL OR expected_r_upper IS NULL
        OR expected_r_lower <= expected_r_upper
    )
);

CREATE INDEX IF NOT EXISTS idx_signal_proposals_generated
    ON financial.signal_proposals (generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_proposals_engine
    ON financial.signal_proposals (strategy_family, producer, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_proposals_symbol
    ON financial.signal_proposals (symbol, generated_at DESC);

CREATE TABLE IF NOT EXISTS financial.signal_proposal_decisions (
    proposal_id        uuid PRIMARY KEY
                       REFERENCES financial.signal_proposals(proposal_id) ON DELETE CASCADE,
    decision           text NOT NULL CHECK (
        decision IN ('SHADOW_ONLY','ALLOCATE','NO_TRADE','REJECT')
    ),
    reason             text NOT NULL,
    decided_at         timestamptz NOT NULL DEFAULT now(),
    allocator_version  text NOT NULL,
    rank_score         double precision
);

CREATE TABLE IF NOT EXISTS financial.shadow_engine_performance (
    proposal_id        uuid PRIMARY KEY
                       REFERENCES financial.signal_proposals(proposal_id) ON DELETE CASCADE,
    status             text NOT NULL CHECK (status IN ('OPEN','CLOSED','CANCELLED')),
    entry_price        double precision NOT NULL,
    stop_price         double precision NOT NULL,
    target_price       double precision NOT NULL,
    exit_price         double precision,
    notional_usd       double precision NOT NULL DEFAULT 1000.0,
    outcome            text,
    r_multiple         double precision,
    mfe_r              double precision,
    mae_r              double precision,
    fees_usd           double precision NOT NULL DEFAULT 0.0,
    funding_usd        double precision NOT NULL DEFAULT 0.0,
    net_pnl_usd        double precision,
    opened_at          timestamptz NOT NULL DEFAULT now(),
    closed_at          timestamptz
);

CREATE INDEX IF NOT EXISTS idx_shadow_status
    ON financial.shadow_engine_performance (status, opened_at);
CREATE INDEX IF NOT EXISTS idx_shadow_closed
    ON financial.shadow_engine_performance (closed_at DESC)
    WHERE status = 'CLOSED';

CREATE OR REPLACE VIEW financial.shadow_engine_scoreboard AS
SELECT
    p.producer,
    p.strategy_family,
    p.strategy_version,
    COALESCE(p.regime, 'UNKNOWN') AS regime,
    count(*) FILTER (WHERE s.status = 'CLOSED') AS closed_n,
    avg(s.r_multiple) FILTER (WHERE s.status = 'CLOSED') AS expectancy_r,
    avg((s.outcome = 'WIN')::int) FILTER (WHERE s.status = 'CLOSED') AS win_rate,
    avg(s.mfe_r) FILTER (WHERE s.status = 'CLOSED') AS avg_mfe_r,
    avg(s.mae_r) FILTER (WHERE s.status = 'CLOSED') AS avg_mae_r,
    sum(s.net_pnl_usd) FILTER (WHERE s.status = 'CLOSED') AS net_pnl_usd
FROM financial.signal_proposals p
LEFT JOIN financial.shadow_engine_performance s USING (proposal_id)
GROUP BY 1,2,3,4;

COMMIT;
