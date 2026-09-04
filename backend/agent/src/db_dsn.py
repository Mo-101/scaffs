"""Single source of truth for resolving the MoStar Postgres DSN.

Callers must resolve through :func:`resolve_dsn` rather than reading
``DATABASE_URL`` directly. The host deployment exports it as a Unix-socket
DSN::

    postgresql:///mostar?host=/var/run/postgresql&port=5433&user=idona

That socket does not exist inside the container, so any module that read the
variable raw got an ``OperationalError`` on every connect while the
environment listing still looked correct. The historical fallback string
``"dbname=mostar port=5433"`` is a socket DSN too -- libpq treats a
keyword/value DSN with no ``host=`` as a Unix-socket connection -- so it fails
the same way.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Optional

import psycopg

logger = logging.getLogger(__name__)

DOCKER_DSN = "postgresql://postgres:mostar@postgres:5432/mostar"
HOST_PORT = os.getenv("POSTGRES_HOST_PORT", "5434")
HOST_DSN = f"postgresql://postgres:mostar@127.0.0.1:{HOST_PORT}/mostar"


def in_container() -> bool:
    """True when running inside the Docker stack."""
    return bool(os.getenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK")) or os.path.exists("/.dockerenv")


def parse_dbname(dsn: str) -> str:
    """Extract the database name from a URL or keyword/value DSN."""
    if "://" in dsn:
        parsed = urllib.parse.urlparse(dsn)
        return parsed.path.lstrip("/").split("?")[0]
    for part in dsn.split():
        if part.startswith("dbname="):
            return part.split("=")[1].strip()
    return ""


def assert_safe_test_database(dsn: str) -> None:
    """Ensure test runs can NEVER execute against a production database.

    Enforces:
      1. Explicit test runtime check (APP_ENV=test or PYTEST_CURRENT_TEST).
      2. Rejection of database named 'mostar'.
      3. Requirement that database name ends with '_test'.
      4. Database marker verification: database must not self-identify as production.
    """
    is_test_env = os.getenv("APP_ENV") == "test" or "PYTEST_CURRENT_TEST" in os.environ
    if not is_test_env:
        return

    dbname = parse_dbname(dsn)
    if dbname == "mostar":
        raise RuntimeError(
            "REFUSING TEST EXECUTION AGAINST PRODUCTION DATABASE: dbname is 'mostar'"
        )

    if not dbname.endswith("_test"):
        raise RuntimeError(
            f"REFUSING TEST EXECUTION: Test database name must end in '_test', got {dbname!r}"
        )

    # Invariant: Verify internal database marker self-identification
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT environment FROM public.system_environment LIMIT 1;"
                )
                row = cur.fetchone()
                if row:
                    env_marker = str(row[0]).strip().lower()
                    if env_marker == "production":
                        raise RuntimeError(
                            "REFUSING TEST EXECUTION: Database self-identifies as 'production'!"
                        )
    except psycopg.OperationalError:
        # If DB connection failed, verify_reachable will handle failure if needed
        pass
    except psycopg.errors.UndefinedTable:
        # Table doesn't exist yet in fresh test DB, which is acceptable
        pass


def verify_reachable(dsn: str) -> None:
    """Verify that an explicitly configured DSN is reachable. Fail hard if unreachable."""
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
    except Exception as exc:
        raise RuntimeError(
            f"Configured database DSN is unreachable: {exc}. Refusing silent fallback."
        ) from exc


def resolve_dsn(dsn: Optional[str] = None, default: Optional[str] = None) -> str:
    """Resolve the DSN to connect with.

    Rule:
      1. Explicit ``dsn`` argument is authoritative.
      2. If ``VIBE_PAPER_DATABASE_URL`` or ``DATABASE_URL`` is set:
         it is authoritative. If unreachable, FAIL. Never substitute another database.
      3. Fallback to discover_default_dsn() only when no explicit config was provided.
      4. Test databases are strictly guarded by :func:`assert_safe_test_database`.
    """
    if dsn:
        assert_safe_test_database(dsn)
        return dsn

    explicit_env = os.getenv("VIBE_PAPER_DATABASE_URL") or os.getenv("DATABASE_URL")
    if explicit_env:
        assert_safe_test_database(explicit_env)
        verify_reachable(explicit_env)
        return explicit_env

    fallback = default or (DOCKER_DSN if in_container() else HOST_DSN)
    assert_safe_test_database(fallback)
    return fallback

