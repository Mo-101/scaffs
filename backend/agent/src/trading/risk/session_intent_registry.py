"""Per-session intent id deduplication for the Step 4 risk gate."""

from __future__ import annotations

import json
from pathlib import Path


class SessionIntentRegistry:
    """Check whether an intent id has already been recorded in this session."""

    def __init__(self, intents_path: str | Path) -> None:
        self.path = Path(intents_path)

    def exists(self, intent_id: str) -> bool:
        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("intent_id") == intent_id:
                return True
        return False
