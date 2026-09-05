"""Runtime settings that operators can flip without restarting anything.

Why this exists: ``SIGMALUI_AUTO_DISPATCH`` / ``IDIM_AUTO_DISPATCH`` are read
from the environment once at process start, so changing auto-execute meant
editing .env, recreating two containers and restarting a PM2 app -- and the
dashboard's own toggle lived in the operator's *browser* localStorage, which no
server flag could reach. The result was three disagreeing controls and a
"paused" system that kept trading.

This module makes one value authoritative and shared: it lives in the same
Postgres every process already talks to, so the API, the worker and the PM2
daemon all read the same flag, and a UI toggle takes effect on the next poll
cycle with no restart.

Env remains the *default* (first-boot / DB-unavailable), never an override:
once a value is set here it wins, so a stale .env cannot silently re-enable
execution.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg

logger = logging.getLogger(__name__)

_TRUTHY = ("1", "true", "yes", "on")

AUTO_DISPATCH_KEY = "auto_dispatch_enabled"

_DDL = """
CREATE SCHEMA IF NOT EXISTS paper_trading;
CREATE TABLE IF NOT EXISTS paper_trading.runtime_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT
);
"""


def _dsn() -> str:
    from src.trading.signal_queue import _get_default_dsn
    return _get_default_dsn()


def _ensure_table(cur) -> None:
    cur.execute(_DDL)


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a setting. Returns ``default`` when unset or the DB is unreachable."""
    try:
        with psycopg.connect(_dsn(), connect_timeout=5) as conn, conn.cursor() as cur:
            _ensure_table(cur)
            cur.execute("SELECT value FROM paper_trading.runtime_settings WHERE key = %s;", (key,))
            row = cur.fetchone()
            conn.commit()
            if row is None:
                return default
            return row[0]
    except Exception as exc:
        # Never let a settings lookup take down a trading loop; fall back to the
        # caller's default (which is the env value) and say so once per call.
        logger.warning("runtime_settings read failed for %r (%s); using default %r", key, exc, default)
        return default


def set_setting(key: str, value: str, updated_by: str = "api") -> None:
    with psycopg.connect(_dsn(), connect_timeout=5) as conn, conn.cursor() as cur:
        _ensure_table(cur)
        cur.execute(
            """
            INSERT INTO paper_trading.runtime_settings (key, value, updated_at, updated_by)
            VALUES (%s, %s, now(), %s)
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value,
                  updated_at = now(),
                  updated_by = EXCLUDED.updated_by;
            """,
            (key, value, updated_by),
        )
        conn.commit()


def auto_dispatch_enabled(env_var: str = "SIGMALUI_AUTO_DISPATCH") -> bool:
    """True when auto-execute is on.

    Precedence: the stored setting wins; ``env_var`` is only the default for a
    system that has never been toggled.
    """
    env_default = "true" if os.getenv(env_var, "false").strip().lower() in _TRUTHY else "false"
    raw = get_setting(AUTO_DISPATCH_KEY, env_default)
    return (raw or "false").strip().lower() in _TRUTHY


def set_auto_dispatch(enabled: bool, updated_by: str = "api") -> bool:
    set_setting(AUTO_DISPATCH_KEY, "true" if enabled else "false", updated_by=updated_by)
    return enabled
