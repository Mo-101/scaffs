"""Append-only JSONL ledger for position protection reconciliation."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LEDGER_DIR = Path(__file__).resolve().parents[3] / "paper_sessions" / "protection_reconcile"
DEFAULT_LEDGER_PATH = LEDGER_DIR / "ledger.jsonl"


class ProtectionLedger:
    """Simple append-only ledger for Step 2 protection reconciliation events."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_LEDGER_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: dict[str, Any]) -> Path:
        """Append one JSON object as a single line."""
        entry = dict(event)
        entry["recorded_at"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(entry, default=str, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.debug("Wrote protection ledger event to %s", self.path)
        return self.path

    def records(self) -> list[dict[str, Any]]:
        """Read all valid records in insertion order."""
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed ledger line: %s", line[:200])
        return out
