"""Per-session trade ledger for the Step 4 cooldown check."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SessionTradeLedger:
    """Read-only per-symbol last-entry timestamp from ``trades.jsonl``."""

    def __init__(self, trades_path: str | Path) -> None:
        self.path = Path(trades_path)

    def last_entry_timestamp(self, symbol: str) -> int | None:
        if not self.path.exists():
            return None
        latest: int | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(record.get("symbol", "")).upper() != symbol.upper():
                continue
            ts = record.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                epoch = int(dt.timestamp())
            except (ValueError, TypeError):
                continue
            latest = epoch if latest is None else max(latest, epoch)
        return latest
