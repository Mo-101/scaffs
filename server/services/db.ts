import { Pool } from "pg";
import dotenv from "dotenv";
import path from "path";
import fs from "fs";

// Load environment variables
if (fs.existsSync(path.resolve("backend/agent/.env"))) {
  dotenv.config({ path: path.resolve("backend/agent/.env") });
}
if (fs.existsSync(path.resolve(".env"))) {
  dotenv.config({ path: path.resolve(".env") });
}

const DATABASE_URL =
  process.env.DATABASE_URL ||
  process.env.NEON_DATABASE_URL ||
  process.env.POSTGRES_URL ||
  process.env.PG_CONNECTION_STRING ||
  "";

let pool: Pool | null = null;
let isConnected = false;
let lastError: string | null = null;

export function getOrCreatePool(): Pool | null {
  if (pool) return pool;
  const dbUrl =
    process.env.DATABASE_URL ||
    process.env.NEON_DATABASE_URL ||
    process.env.POSTGRES_URL ||
    process.env.PG_CONNECTION_STRING ||
    "";

  if (!dbUrl) return null;

  try {
    pool = new Pool({
      connectionString: dbUrl,
      ssl: dbUrl.includes("neon.tech") || dbUrl.includes("sslmode=require")
        ? { rejectUnauthorized: false }
        : false,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
      keepAlive: true,
      keepAliveInitialDelayMillis: 10000,
    });

    pool.on("error", (err) => {
      lastError = err?.message || "Postgres pool connection drop";
      isConnected = false;
      console.warn("⚠️ Neon DB pool connection drop detected; auto-reconnecting on next heartbeat:", err?.message);
    });

    return pool;
  } catch (err: any) {
    lastError = err?.message || "Failed to initialize postgres pool";
    return null;
  }
}

// Initial attempt
getOrCreatePool();

export async function getDbStatus() {
  if (!pool) {
    return {
      connected: false,
      driver: "in_memory_fallback",
      database_url_configured: Boolean(DATABASE_URL),
      provider: "Neon DB (Configurable via DATABASE_URL)",
      last_error: lastError || (DATABASE_URL ? "Pool not initialized" : "DATABASE_URL not set in environment"),
      tables_synced: false,
    };
  }

  try {
    const client = await pool.connect();
    try {
      const res = await client.query("SELECT NOW() as now, current_database() as db_name, version() as pg_version;");
      isConnected = true;
      lastError = null;

      // Check tables count
      const tablesRes = await client.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' OR table_schema = 'paper_trading'
      `);

      return {
        connected: true,
        driver: "neon_postgres",
        database_url_configured: true,
        provider: "Neon DB Cloud PostgreSQL",
        database_name: res.rows[0]?.db_name,
        postgres_version: res.rows[0]?.pg_version?.split(" ")[0] || "PostgreSQL",
        server_time: res.rows[0]?.now,
        tables_count: tablesRes.rowCount || 0,
        tables: tablesRes.rows.map((r: any) => r.table_name),
        tables_synced: true,
      };
    } finally {
      client.release();
    }
  } catch (err: any) {
    isConnected = false;
    lastError = err?.message || "Failed to connect to database";
    return {
      connected: false,
      driver: "in_memory_fallback",
      database_url_configured: Boolean(DATABASE_URL),
      provider: "Neon DB Cloud PostgreSQL",
      last_error: lastError,
      tables_synced: false,
    };
  }
}

// Initialize tables if connected
export async function initDatabaseSchemas() {
  if (!pool) return false;
  try {
    const client = await pool.connect();
    try {
      await client.query(`
        CREATE SCHEMA IF NOT EXISTS paper_trading;

        CREATE TABLE IF NOT EXISTS paper_trading.trading_accounts (
          account_id VARCHAR(64) PRIMARY KEY,
          strategy_id VARCHAR(64) NOT NULL,
          worker_id VARCHAR(64) UNIQUE NOT NULL,
          timeframe VARCHAR(16) NOT NULL,
          mode VARCHAR(16) NOT NULL DEFAULT 'paper',
          leverage INT NOT NULL DEFAULT 5,
          initial_capital NUMERIC NOT NULL DEFAULT 10000,
          cash_balance NUMERIC NOT NULL DEFAULT 10000,
          realized_pnl NUMERIC NOT NULL DEFAULT 0,
          funding_pnl NUMERIC NOT NULL DEFAULT 0,
          fees NUMERIC NOT NULL DEFAULT 0,
          margin_used NUMERIC NOT NULL DEFAULT 0,
          unrealized_pnl NUMERIC NOT NULL DEFAULT 0,
          current_equity NUMERIC NOT NULL DEFAULT 10000,
          ledger_status VARCHAR(32) NOT NULL DEFAULT 'in_sync',
          last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          last_trade TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS paper_trading.closed_trades (
          trade_id VARCHAR(64) PRIMARY KEY,
          account_id VARCHAR(64) NOT NULL,
          worker_id VARCHAR(64) NOT NULL,
          symbol VARCHAR(32) NOT NULL,
          side VARCHAR(16) NOT NULL,
          leverage INT NOT NULL,
          margin_used NUMERIC NOT NULL,
          notional NUMERIC NOT NULL,
          quantity NUMERIC NOT NULL,
          entry_time TIMESTAMP WITH TIME ZONE NOT NULL,
          exit_time TIMESTAMP WITH TIME ZONE NOT NULL,
          entry_price NUMERIC NOT NULL,
          exit_price NUMERIC NOT NULL,
          gross_pnl NUMERIC NOT NULL,
          fees NUMERIC NOT NULL,
          funding_paid NUMERIC NOT NULL DEFAULT 0,
          net_pnl NUMERIC NOT NULL,
          roi_pct NUMERIC NOT NULL,
          hold_seconds INT NOT NULL,
          entry_reason TEXT,
          exit_reason TEXT,
          market_regime VARCHAR(32),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS paper_trading.grid_state (
          worker_id VARCHAR(64) PRIMARY KEY,
          symbol VARCHAR(32) NOT NULL,
          upper_bound NUMERIC NOT NULL,
          lower_bound NUMERIC NOT NULL,
          grid_levels INT NOT NULL,
          spacing_pct NUMERIC NOT NULL,
          active_orders_count INT NOT NULL,
          completed_cycles INT NOT NULL,
          realized_grid_profit NUMERIC NOT NULL,
          grid_apr_pct NUMERIC NOT NULL,
          active_bids JSONB,
          active_asks JSONB,
          open_position JSONB,
          grid_config JSONB,
          state_checksum VARCHAR(64),
          state_sequence BIGINT DEFAULT 1,
          last_fill_at TIMESTAMP WITH TIME ZONE,
          last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        -- Safe Alter Migrations for existing deployments
        ALTER TABLE paper_trading.grid_state ADD COLUMN IF NOT EXISTS open_position JSONB;
        ALTER TABLE paper_trading.grid_state ADD COLUMN IF NOT EXISTS grid_config JSONB;
        ALTER TABLE paper_trading.grid_state ADD COLUMN IF NOT EXISTS state_checksum VARCHAR(64);
        ALTER TABLE paper_trading.grid_state ADD COLUMN IF NOT EXISTS state_sequence BIGINT DEFAULT 1;

        CREATE TABLE IF NOT EXISTS paper_trading.morning_glory_state (
          worker_id VARCHAR(64) PRIMARY KEY,
          primary_symbol VARCHAR(32) NOT NULL,
          current_zscore NUMERIC NOT NULL,
          active_arbitrage_legs INT NOT NULL,
          next_settlement_time TIMESTAMP WITH TIME ZONE,
          accumulated_funding NUMERIC NOT NULL,
          annualized_yield_pct NUMERIC NOT NULL,
          symbols_zscores JSONB,
          last_settlement_at TIMESTAMP WITH TIME ZONE,
          last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
      `);
      return true;
    } finally {
      client.release();
    }
  } catch (err: any) {
    console.error("Database schema init failed:", err?.message);
    return false;
  }
}

export async function syncSessionToDb(session: any) {
  const activePool = getOrCreatePool();
  if (!activePool) return false;
  try {
    const client = await activePool.connect();
    try {
      const acc = session.database_account;
      if (!acc) return false;

      // 1. Sync Trading Account Ledger
      await client.query(`
        INSERT INTO paper_trading.trading_accounts (
          account_id, strategy_id, worker_id, timeframe, mode, leverage,
          initial_capital, cash_balance, realized_pnl, funding_pnl, fees,
          margin_used, unrealized_pnl, current_equity, ledger_status,
          last_heartbeat, last_trade, updated_at
        ) VALUES (
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW()
        )
        ON CONFLICT (worker_id) DO UPDATE SET
          cash_balance = EXCLUDED.cash_balance,
          realized_pnl = EXCLUDED.realized_pnl,
          funding_pnl = EXCLUDED.funding_pnl,
          fees = EXCLUDED.fees,
          margin_used = EXCLUDED.margin_used,
          unrealized_pnl = EXCLUDED.unrealized_pnl,
          current_equity = EXCLUDED.current_equity,
          ledger_status = EXCLUDED.ledger_status,
          last_heartbeat = EXCLUDED.last_heartbeat,
          last_trade = EXCLUDED.last_trade,
          updated_at = NOW();
      `, [
        acc.account_id || `acc_${session.session_id}`,
        acc.strategy_id || session.session.strategy_id,
        acc.worker_id || session.session_id,
        acc.timeframe || session.session.timeframe,
        acc.mode || "paper",
        acc.leverage || session.session.risk_config.leverage || 5,
        acc.initial_capital || session.session.initial_cash || 10000,
        acc.cash_available || 10000,
        acc.realized_pnl || 0,
        acc.funding_pnl || 0,
        acc.fees || 0,
        acc.margin_used || 0,
        acc.unrealized_pnl || 0,
        acc.current_equity || 10000,
        acc.ledger_status || "in_sync",
        acc.last_heartbeat || new Date().toISOString(),
        acc.last_trade || new Date().toISOString(),
      ]);

      // 2. Sync Grid Futures Runner State if present
      if (session.grid_engine) {
        const grid = session.grid_engine;
        await client.query(`
          INSERT INTO paper_trading.grid_state (
            worker_id, symbol, upper_bound, lower_bound, grid_levels, spacing_pct,
            active_orders_count, completed_cycles, realized_grid_profit, grid_apr_pct,
            active_bids, active_asks, last_fill_at, last_updated
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW()
          )
          ON CONFLICT (worker_id) DO UPDATE SET
            symbol = EXCLUDED.symbol,
            upper_bound = EXCLUDED.upper_bound,
            lower_bound = EXCLUDED.lower_bound,
            grid_levels = EXCLUDED.grid_levels,
            spacing_pct = EXCLUDED.spacing_pct,
            active_orders_count = EXCLUDED.active_orders_count,
            completed_cycles = EXCLUDED.completed_cycles,
            realized_grid_profit = EXCLUDED.realized_grid_profit,
            grid_apr_pct = EXCLUDED.grid_apr_pct,
            active_bids = EXCLUDED.active_bids,
            active_asks = EXCLUDED.active_asks,
            last_fill_at = EXCLUDED.last_fill_at,
            last_updated = NOW();
        `, [
          session.session_id,
          grid.symbol || "SOL-USDT",
          grid.upper_bound || 200,
          grid.lower_bound || 170,
          grid.grid_levels || 20,
          grid.spacing_pct || 0.006,
          (grid.active_bids?.length || 0) + (grid.active_asks?.length || 0),
          grid.completed_cycles || 0,
          grid.realized_grid_profit || 0,
          grid.grid_apr_pct || 40,
          JSON.stringify(grid.active_bids || []),
          JSON.stringify(grid.active_asks || []),
          grid.last_fill_at ? new Date(grid.last_fill_at) : null,
        ]);
      }

      // 3. Sync Morning Glory Funding State if present
      if (session.morning_glory) {
        const mg = session.morning_glory;
        await client.query(`
          INSERT INTO paper_trading.morning_glory_state (
            worker_id, primary_symbol, current_zscore, active_arbitrage_legs,
            accumulated_funding, annualized_yield_pct, symbols_zscores,
            last_settlement_at, last_updated
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, NOW()
          )
          ON CONFLICT (worker_id) DO UPDATE SET
            primary_symbol = EXCLUDED.primary_symbol,
            current_zscore = EXCLUDED.current_zscore,
            active_arbitrage_legs = EXCLUDED.active_arbitrage_legs,
            accumulated_funding = EXCLUDED.accumulated_funding,
            annualized_yield_pct = EXCLUDED.annualized_yield_pct,
            symbols_zscores = EXCLUDED.symbols_zscores,
            last_settlement_at = EXCLUDED.last_settlement_at,
            last_updated = NOW();
        `, [
          session.session_id,
          "SOL-USDT",
          mg.symbols_zscores?.[0]?.zscore || 2.5,
          mg.symbols_zscores?.filter((s: any) => s.signal !== "neutral").length || 3,
          mg.total_funding_harvested || 0,
          mg.annualized_yield_pct || 35,
          JSON.stringify(mg.symbols_zscores || []),
          mg.last_settlement_at ? new Date(mg.last_settlement_at) : null,
        ]);
      }

      // 4. Batch sync recent closed trades (upsert first 5)
      if (Array.isArray(session.recent_trades) && session.recent_trades.length > 0) {
        for (const trade of session.recent_trades.slice(0, 5)) {
          if (!trade.trade_id) continue;
          await client.query(`
            INSERT INTO paper_trading.closed_trades (
              trade_id, account_id, worker_id, symbol, side, leverage, margin_used,
              notional, quantity, entry_time, exit_time, entry_price, exit_price,
              gross_pnl, fees, funding_paid, net_pnl, roi_pct, hold_seconds,
              entry_reason, exit_reason, market_regime, created_at
            ) VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, NOW()
            )
            ON CONFLICT (trade_id) DO NOTHING;
          `, [
            trade.trade_id,
            acc.account_id || `acc_${session.session_id}`,
            session.session_id,
            trade.symbol,
            trade.side,
            trade.leverage || 5,
            trade.margin_used || 1000,
            trade.notional || 5000,
            trade.quantity || 1,
            trade.entry_time || new Date().toISOString(),
            trade.exit_time || new Date().toISOString(),
            trade.entry_price || 100,
            trade.exit_price || 105,
            trade.gross_pnl || 0,
            (trade.entry_fee || 0) + (trade.exit_fee || 0),
            trade.funding_paid || 0,
            trade.net_pnl || 0,
            trade.roi_pct || 0,
            trade.hold_seconds || 3600,
            trade.entry_reason || "Signal Triggered",
            trade.exit_reason || "Target Hit",
            trade.market_regime || "trend",
          ]);
        }
      }

      return true;
    } finally {
      client.release();
    }
  } catch (err: any) {
    lastError = err?.message || "Failed during DB sync";
    return false;
  }
}

/**
 * Recovers persisted Grid & Worker states from Neon DB after a restart or disconnect
 */
export async function recoverPersistedSessions(sessionsMap: Map<string, any>) {
  const activePool = getOrCreatePool();
  if (!activePool) return { recovered: 0, message: "No database configured" };

  try {
    const client = await activePool.connect();
    try {
      let recoveredCount = 0;

      // 1. Recover Grid states
      const gridRes = await client.query(`SELECT * FROM paper_trading.grid_state`);
      for (const row of gridRes.rows) {
        const session = sessionsMap.get(row.worker_id);
        if (session && session.grid_engine) {
          session.grid_engine.upper_bound = Number(row.upper_bound);
          session.grid_engine.lower_bound = Number(row.lower_bound);
          session.grid_engine.grid_levels = Number(row.grid_levels);
          session.grid_engine.spacing_pct = Number(row.spacing_pct);
          session.grid_engine.completed_cycles = Number(row.completed_cycles);
          session.grid_engine.realized_grid_profit = Number(row.realized_grid_profit);
          session.grid_engine.grid_apr_pct = Number(row.grid_apr_pct);
          if (row.active_bids && Array.isArray(row.active_bids)) {
            session.grid_engine.active_bids = row.active_bids;
          }
          if (row.active_asks && Array.isArray(row.active_asks)) {
            session.grid_engine.active_asks = row.active_asks;
          }
          if (row.last_fill_at) {
            session.grid_engine.last_fill_at = new Date(row.last_fill_at).toISOString();
          }
          if (row.open_position && session.latest_mark?.open_positions) {
            const posIdx = session.latest_mark.open_positions.findIndex((p: any) => p.symbol === row.symbol);
            if (posIdx >= 0) {
              session.latest_mark.open_positions[posIdx] = {
                ...session.latest_mark.open_positions[posIdx],
                ...row.open_position,
              };
            }
          }
          recoveredCount++;
        }
      }

      // 2. Recover Trading Accounts & Ledger
      const accRes = await client.query(`SELECT * FROM paper_trading.trading_accounts`);
      for (const row of accRes.rows) {
        const session = sessionsMap.get(row.worker_id);
        if (session && session.database_account) {
          session.database_account.realized_pnl = Number(row.realized_pnl);
          session.database_account.funding_pnl = Number(row.funding_pnl);
          session.database_account.fees = Number(row.fees);
          session.database_account.current_equity = Number(row.current_equity);
          session.database_account.cash_available = Number(row.cash_balance);
          session.database_account.ledger_status = row.ledger_status || "in_sync";
          recoveredCount++;
        }
      }

      console.log(`✅ Graceful recovery completed: Restored state for ${recoveredCount} records from Neon DB.`);
      return { recovered: recoveredCount, message: `Successfully restored state from Neon DB` };
    } finally {
      client.release();
    }
  } catch (err: any) {
    console.warn("State recovery skipped or partially failed:", err?.message);
    return { recovered: 0, message: err?.message };
  }
}

/**
 * Computes a deterministic state checksum to ensure idempotency and skip redundant DB transactions
 */
export function computeGridStateChecksum(grid: any, openPos: any, realizedPnl: number): string {
  const payload = [
    grid?.symbol || "",
    Number(grid?.upper_bound || 0).toFixed(4),
    Number(grid?.lower_bound || 0).toFixed(4),
    grid?.grid_levels || 0,
    grid?.completed_cycles || 0,
    Number(grid?.realized_grid_profit || 0).toFixed(2),
    Number(realizedPnl || 0).toFixed(2),
    grid?.last_fill_at || "",
    openPos ? `${openPos.symbol}_${openPos.side}_${openPos.quantity}_${openPos.entry_price}` : "no_pos",
  ].join("|");

  let hash = 0;
  for (let i = 0; i < payload.length; i++) {
    const chr = payload.charCodeAt(i);
    hash = (hash << 5) - hash + chr;
    hash |= 0;
  }
  return `chk_${Math.abs(hash).toString(16)}`;
}

// In-memory cache of last synced checksum per worker to avoid redundant SQL transaction locks
const LAST_GRID_CHECKSUMS = new Map<string, string>();

/**
 * Idempotent Async Transaction state save for Grid Future Runners
 * Serializes configuration, ladder bounds, active rungs, open position, and account equity in an atomic transaction.
 */
export async function saveGridRunnerStateTransaction(
  workerId: string,
  session: any,
  force: boolean = false
): Promise<{ ok: boolean; idempotent_skipped?: boolean; checksum?: string; last_updated?: string; error?: string }> {
  if (!session || !session.grid_engine) {
    return { ok: false, error: "No grid engine found on session" };
  }

  const grid = session.grid_engine;
  const acc = session.database_account || {};
  const openPos = session.latest_mark?.open_positions?.find((p: any) => p.symbol === grid.symbol) || session.latest_mark?.open_positions?.[0];

  const checksum = computeGridStateChecksum(grid, openPos, acc.realized_pnl || 0);

  // Idempotency check: Skip SQL execution if state has not mutated since last save
  if (!force && LAST_GRID_CHECKSUMS.get(workerId) === checksum) {
    return { ok: true, idempotent_skipped: true, checksum };
  }

  const activePool = getOrCreatePool();
  if (!activePool) {
    LAST_GRID_CHECKSUMS.set(workerId, checksum);
    return { ok: true, idempotent_skipped: false, checksum, last_updated: new Date().toISOString() };
  }

  try {
    const client = await activePool.connect();
    try {
      // Begin Atomic Transaction
      await client.query("BEGIN;");

      const nowIso = new Date().toISOString();
      const openPositionPayload = openPos
        ? {
            symbol: openPos.symbol,
            side: openPos.side,
            quantity: openPos.quantity,
            entry_price: openPos.entry_price,
            mark_price: openPos.mark_price,
            liquidation_price: openPos.liquidation_price,
            unrealized_gross_pnl: openPos.unrealized_gross_pnl,
            unrealized_net_pnl: openPos.unrealized_net_pnl,
            margin_roi_pct: openPos.margin_roi_pct,
            isolated_margin: openPos.isolated_margin,
            leverage: openPos.leverage,
          }
        : null;

      const gridConfigPayload = {
        strategy_type: session.session?.strategy_type || "bounded_grid_v1",
        timeframe: session.session?.timeframe || "tick",
        leverage: session.session?.risk_config?.leverage || 5,
        fee_rate: session.session?.fee_rate || 0.0004,
        source: session.session?.source || "okx",
        price_kind: session.session?.price_kind || "mark_price",
      };

      // 1. Idempotently Upsert Grid Runner State
      await client.query(`
        INSERT INTO paper_trading.grid_state (
          worker_id, symbol, upper_bound, lower_bound, grid_levels, spacing_pct,
          active_orders_count, completed_cycles, realized_grid_profit, grid_apr_pct,
          active_bids, active_asks, open_position, grid_config, state_checksum,
          last_fill_at, last_updated
        ) VALUES (
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW()
        )
        ON CONFLICT (worker_id) DO UPDATE SET
          symbol = EXCLUDED.symbol,
          upper_bound = EXCLUDED.upper_bound,
          lower_bound = EXCLUDED.lower_bound,
          grid_levels = EXCLUDED.grid_levels,
          spacing_pct = EXCLUDED.spacing_pct,
          active_orders_count = EXCLUDED.active_orders_count,
          completed_cycles = EXCLUDED.completed_cycles,
          realized_grid_profit = EXCLUDED.realized_grid_profit,
          grid_apr_pct = EXCLUDED.grid_apr_pct,
          active_bids = EXCLUDED.active_bids,
          active_asks = EXCLUDED.active_asks,
          open_position = EXCLUDED.open_position,
          grid_config = EXCLUDED.grid_config,
          state_checksum = EXCLUDED.state_checksum,
          state_sequence = paper_trading.grid_state.state_sequence + 1,
          last_fill_at = EXCLUDED.last_fill_at,
          last_updated = NOW();
      `, [
        workerId,
        grid.symbol || "SOL-USDT",
        grid.upper_bound || 200,
        grid.lower_bound || 170,
        grid.grid_levels || 20,
        grid.spacing_pct || 0.006,
        (grid.active_bids?.length || 0) + (grid.active_asks?.length || 0),
        grid.completed_cycles || 0,
        grid.realized_grid_profit || 0,
        grid.grid_apr_pct || 40,
        JSON.stringify(grid.active_bids || []),
        JSON.stringify(grid.active_asks || []),
        JSON.stringify(openPositionPayload),
        JSON.stringify(gridConfigPayload),
        checksum,
        grid.last_fill_at ? new Date(grid.last_fill_at) : null,
      ]);

      // 2. Atomically Upsert Associated Trading Account Ledger
      if (acc.account_id || workerId) {
        await client.query(`
          INSERT INTO paper_trading.trading_accounts (
            account_id, strategy_id, worker_id, timeframe, mode, leverage,
            initial_capital, cash_balance, realized_pnl, funding_pnl, fees,
            margin_used, unrealized_pnl, current_equity, ledger_status,
            last_heartbeat, last_trade, updated_at
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW(), NOW(), NOW()
          )
          ON CONFLICT (worker_id) DO UPDATE SET
            cash_balance = EXCLUDED.cash_balance,
            realized_pnl = EXCLUDED.realized_pnl,
            funding_pnl = EXCLUDED.funding_pnl,
            fees = EXCLUDED.fees,
            margin_used = EXCLUDED.margin_used,
            unrealized_pnl = EXCLUDED.unrealized_pnl,
            current_equity = EXCLUDED.current_equity,
            ledger_status = EXCLUDED.ledger_status,
            last_heartbeat = NOW(),
            updated_at = NOW();
        `, [
          acc.account_id || `acc_${workerId}`,
          acc.strategy_id || session.session?.strategy_id || "bounded_grid_v1",
          workerId,
          acc.timeframe || session.session?.timeframe || "tick",
          acc.mode || "paper",
          acc.leverage || session.session?.risk_config?.leverage || 5,
          acc.initial_capital || session.session?.initial_cash || 5000,
          acc.cash_available || 5000,
          acc.realized_pnl || 0,
          acc.funding_pnl || 0,
          acc.fees || 0,
          acc.margin_used || 0,
          acc.unrealized_pnl || 0,
          acc.current_equity || 5000,
          acc.ledger_status || "in_sync",
        ]);
      }

      // Commit Atomic Transaction
      await client.query("COMMIT;");

      LAST_GRID_CHECKSUMS.set(workerId, checksum);
      return { ok: true, checksum, last_updated: nowIso };
    } catch (err: any) {
      await client.query("ROLLBACK;");
      lastError = err?.message || "Grid state transaction rollback";
      console.error(`❌ Transaction rollback on grid runner ${workerId}:`, err?.message);
      return { ok: false, error: err?.message };
    } finally {
      client.release();
    }
  } catch (err: any) {
    lastError = err?.message || "Pool acquire failure during grid save";
    return { ok: false, error: err?.message };
  }
}

/**
 * Queries the last known serialized state for a specific Grid runner
 */
export async function getGridRunnerLastKnownState(workerId: string) {
  const activePool = getOrCreatePool();
  if (!activePool) return null;

  try {
    const client = await activePool.connect();
    try {
      const res = await client.query(
        `SELECT * FROM paper_trading.grid_state WHERE worker_id = $1 LIMIT 1`,
        [workerId]
      );
      if (res.rows.length === 0) return null;

      const row = res.rows[0];
      return {
        worker_id: row.worker_id,
        symbol: row.symbol,
        upper_bound: Number(row.upper_bound),
        lower_bound: Number(row.lower_bound),
        grid_levels: Number(row.grid_levels),
        spacing_pct: Number(row.spacing_pct),
        active_orders_count: Number(row.active_orders_count),
        completed_cycles: Number(row.completed_cycles),
        realized_grid_profit: Number(row.realized_grid_profit),
        grid_apr_pct: Number(row.grid_apr_pct),
        active_bids: row.active_bids || [],
        active_asks: row.active_asks || [],
        open_position: row.open_position || null,
        grid_config: row.grid_config || null,
        state_checksum: row.state_checksum,
        state_sequence: Number(row.state_sequence || 1),
        last_fill_at: row.last_fill_at ? new Date(row.last_fill_at).toISOString() : null,
        last_updated: row.last_updated ? new Date(row.last_updated).toISOString() : null,
      };
    } finally {
      client.release();
    }
  } catch (err: any) {
    console.warn(`Failed to query last known state for ${workerId}:`, err?.message);
    return null;
  }
}

