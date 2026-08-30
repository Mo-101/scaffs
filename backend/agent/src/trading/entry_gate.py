"""The new-entry kill switch.

``NEW_ENTRIES_ENABLED`` was set in ``.env`` and appended by every deploy
script, but no application code read it. Setting it to ``false`` therefore
halted nothing: on 2026-08-30 twelve entries were dispatched into live
testnet positions during an hour in which the flag read ``false`` in the
running container. This module is the single reader that makes it real.

The check belongs at the last common order-submission boundary
(``BinanceTestnetExecutor._submit_real``) rather than in each caller. Every
new-entry route -- the bulk Idim sync, UI dispatch, and the direct
``/paper-sessions/binance-testnet/order`` endpoint -- funnels through
``SignalQueueManager.dispatch_queued_signal`` into that one method, so
enforcing there cannot be bypassed by adding another caller later.

Reduce-only traffic is deliberately NOT gated. Halting new risk must never
prevent closing or protecting a position that is already open; protective
STOP_MARKET/TAKE_PROFIT_MARKET orders and reduce-only closes reach the
exchange through other modules and stay unaffected by this flag.
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}

#: Terminal status recorded when the kill switch refuses an entry.
NEW_ENTRIES_DISABLED_STATUS = "NEW_ENTRIES_DISABLED"


def new_entries_enabled() -> bool:
    """True when new entries may reach the exchange.

    Unset means enabled -- the historical default, so environments that never
    configured the flag (tests, local dev) behave as they always have. Only an
    explicit falsy value halts, which is what an operator setting
    ``NEW_ENTRIES_ENABLED=false`` intends.
    """
    raw = os.getenv("NEW_ENTRIES_ENABLED")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in _TRUTHY


def new_entry_block_reason() -> str:
    return (
        "NEW_ENTRIES_DISABLED: NEW_ENTRIES_ENABLED is false; new entries are halted. "
        "Closing and protecting existing positions is unaffected."
    )
