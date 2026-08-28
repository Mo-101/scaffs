"""Point every DB-backed test at an isolated database before any test module imports.

`SignalQueueManager`, `_paper_dsn()` (paper_session_routes.py), and
`idim_feed_bridge.DEFAULT_DSN` each independently fall back to the literal
`dbname=mostar port=5433` -- the same database the live dev dashboard reads --
whenever `VIBE_PAPER_DATABASE_URL`/`DATABASE_URL` aren't set. Three test files
(test_signal_queue.py, test_signal_queue_dispatch.py,
test_signal_queue_lifecycle.py) do exactly that with no cleanup, which is why
~40 stale worker_id rows from unit test runs were found sitting permanently in
paper_trading.paper_cycle_events on the dev DB.

This has to be a plain module-level assignment, not a fixture. idim_feed_bridge
binds its DEFAULT_DSN as a function-default at import time, so a fixture-time
monkeypatch (which runs at test setup, after imports already happened) would be
too late for any test that imports it at module scope. conftest.py is always
imported by pytest before any test module in its directory, so this runs first.

One-time setup for a fresh checkout: `mostar_test` must exist and have the
paper_trading schema applied (migrations/*.sql, then
scratch/create_signal_queue_table.py pointed at mostar_test instead of mostar).
"""

import os

os.environ["VIBE_PAPER_DATABASE_URL"] = "dbname=mostar_test port=5433"
