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

import os
from typing import Optional

DOCKER_DSN = "postgresql://postgres:mostar@postgres:5432/mostar"
HOST_PORT = os.getenv("POSTGRES_HOST_PORT", "5434")
HOST_DSN = f"postgresql://postgres:mostar@127.0.0.1:{HOST_PORT}/mostar"

_HOST_SOCKET_MARKER = "/var/run/postgresql"


def in_container() -> bool:
    """True when running inside the Docker stack."""
    return bool(os.getenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK")) or os.path.exists("/.dockerenv")


def is_unix_socket_dsn(dsn: str) -> bool:
    """True for DSNs that reach Postgres over a Unix socket rather than TCP."""
    if _HOST_SOCKET_MARKER in dsn:
        return True
    # Keyword/value form with no host= (e.g. "dbname=mostar port=5433").
    return "://" not in dsn and "host=" not in dsn


def _reachable(dsn: str) -> str:
    """Swap a socket DSN for the TCP endpoint that is actually reachable here."""
    if not is_unix_socket_dsn(dsn):
        return dsn
    return DOCKER_DSN if in_container() else HOST_DSN


def resolve_dsn(dsn: Optional[str] = None, default: Optional[str] = None) -> str:
    """Resolve the DSN to connect with.

    Precedence: explicit ``dsn`` argument, ``VIBE_PAPER_DATABASE_URL``,
    ``DATABASE_URL``, the caller's ``default``, then the built-in endpoint for
    this environment. Every candidate except an explicit ``dsn`` is rewritten
    when it names a Unix socket that is unreachable from here.
    """
    if dsn:
        return dsn

    for candidate in (os.getenv("VIBE_PAPER_DATABASE_URL"), os.getenv("DATABASE_URL"), default):
        if candidate:
            return _reachable(candidate)

    return DOCKER_DSN if in_container() else HOST_DSN
