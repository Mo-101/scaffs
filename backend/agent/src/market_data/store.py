"""Unified, DB-backed market data store for live exchange snapshots.

Stores per-provider, per-kind, per-symbol JSONB snapshots. Keeps the most
recent payload only (no time-series), so the DB stays small.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from psycopg.types.json import Json

logger = logging.getLogger(__name__)

DEFAULT_DSN = "dbname=mostar port=5433"


_MARKET_DATA_SCHEMA = """
CREATE SCHEMA IF NOT EXISTS market_data;

CREATE TABLE IF NOT EXISTS market_data.provider_status (
    provider TEXT PRIMARY KEY,
    last_sync TIMESTAMPTZ,
    status TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS market_data.raw_snapshots (
    provider TEXT NOT NULL,
    kind TEXT NOT NULL,
    symbol TEXT,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, kind, symbol)
);

CREATE INDEX IF NOT EXISTS idx_raw_snapshots_symbol
    ON market_data.raw_snapshots (symbol);

CREATE INDEX IF NOT EXISTS idx_raw_snapshots_provider_symbol
    ON market_data.raw_snapshots (provider, symbol);
"""


class MarketDataStore:
    """Compact, single-row-per-snapshot store for all exchange market data."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DSN
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(_MARKET_DATA_SCHEMA)
            conn.commit()

    def upsert(
        self,
        provider: str,
        kind: str,
        symbol: Optional[str],
        payload: dict[str, Any],
    ) -> None:
        """Write or overwrite a snapshot for (provider, kind, symbol)."""
        symbol = symbol or "_global"
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_data.raw_snapshots (provider, kind, symbol, payload, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (provider, kind, symbol) DO UPDATE
                  SET payload = EXCLUDED.payload,
                      updated_at = now();
                """,
                (provider, kind, symbol, Json(payload)),
            )
            conn.commit()

    def set_status(self, provider: str, status: str, error: Optional[str] = None) -> None:
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_data.provider_status (provider, last_sync, status, error)
                VALUES (%s, now(), %s, %s)
                ON CONFLICT (provider) DO UPDATE
                  SET last_sync = EXCLUDED.last_sync,
                      status = EXCLUDED.status,
                      error = EXCLUDED.error;
                """,
                (provider, status, error),
            )
            conn.commit()

    def get(
        self,
        provider: str,
        kind: str,
        symbol: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        symbol = symbol or "_global"
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload, updated_at FROM market_data.raw_snapshots
                WHERE provider = %s AND kind = %s AND symbol = %s;
                """,
                (provider, kind, symbol),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"payload": row[0], "updated_at": row[1].isoformat() if row[1] else None}

    def list_symbols(self, provider: str, kind: str) -> list[str]:
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol FROM market_data.raw_snapshots
                WHERE provider = %s AND kind = %s AND symbol <> '_global'
                ORDER BY symbol;
                """,
                (provider, kind),
            )
            return [r[0] for r in cur.fetchall()]

    def get_status(self, provider: Optional[str] = None) -> list[dict[str, Any]]:
        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            if provider:
                cur.execute(
                    "SELECT provider, last_sync, status, error FROM market_data.provider_status WHERE provider = %s;",
                    (provider,),
                )
            else:
                cur.execute("SELECT provider, last_sync, status, error FROM market_data.provider_status;")
            return [
                {
                    "provider": r[0],
                    "last_sync": r[1].isoformat() if r[1] else None,
                    "status": r[2],
                    "error": r[3],
                }
                for r in cur.fetchall()
            ]
