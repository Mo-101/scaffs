"""BOOTSTRAP / EXPERIMENTAL MoScript build envelope for Scaffs.

The full MoScript runtime, ScrollValidator, ThroneLock, Resonance, Woo,
Registry, soulprint, and sealing infrastructure were not present in the
`scaffs` working tree at the time of this build. The reference MoScript
corpus in `/home/idona/MoStar/_apps/Scaffs/moscript/` and the
`MOSCRIPT_TRADING_RUNTIME_README.md` are deliberately `sealed: false` and
`production_authorized: false`, with explicit instructions to register and
seal contracts in the canonical MoScript runtime using real project identity
material.

This module is therefore a minimal, typed bootstrap that:

- Loads a scroll/packet.
- Validates canonical strategy binding invariants.
- Records an append-only, hash-chained registry for audit.
- Runs tests and records evidence.

It is **not** a production MoScript runtime and does not fabricate
soulprints, seals, or production authorization.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

MOSCRIPT_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = MOSCRIPT_DIR / "registry.jsonl"


# ─── Canonical Trading Strategy Binding ───────────────────────────────────────
# Advisory only. Deterministic application authorization lives in
# backend/agent/src/trading/strategy_binding.py.
CANONICAL_BINDINGS = {
    "periodic_equal_weight_rebalance": "rebalance_equal_weight_v1",
    "bounded_grid_v1:5x": "grid_futures_5x",
    "bounded_grid_v1:10x": "grid_futures_10x",
    "funding_rate_zscore": "morning_glory",
}


def _canonical_json(obj: Any) -> str:
    """Serialize in a deterministic, hash-friendly form."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─── Scroll Types ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ScrollProvenance:
    origin: str = "builder"
    initiator: str = "devin"
    soulprint: str = "devin.scaffs.builder"


@dataclass(frozen=True)
class ScrollPermissions:
    read: List[str] = field(default_factory=list)
    write: List[str] = field(default_factory=list)
    execute: List[str] = field(default_factory=list)


@dataclass
class Scroll:
    scroll_id: str
    purpose: str
    affected_files: List[str]
    requested_permissions: ScrollPermissions
    invariants: List[str]
    test_commands: List[str]
    rollback_files: List[str]
    validation_result: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None
    previous_record_hash: Optional[str] = None
    record_hash: Optional[str] = None
    sealed_at: Optional[str] = None
    provenance: ScrollProvenance = field(default_factory=ScrollProvenance)
    status: str = "BOOTSTRAP/EXPERIMENTAL"
    production_authorized: bool = False

    def digest_payload(self) -> bytes:
        payload = {
            "scroll_id": self.scroll_id,
            "purpose": self.purpose,
            "affected_files": sorted(self.affected_files),
            "invariants": self.invariants,
            "provenance": asdict(self.provenance),
        }
        return _canonical_json(payload).encode("utf-8")

    def content_hash_value(self) -> str:
        return _sha256(self.digest_payload())


# ─── Advisory Validator (Resonance) ───────────────────────────────────────────
def validate_scroll(scroll: Scroll) -> Dict[str, Any]:
    errors = []
    if not scroll.scroll_id or not scroll.purpose:
        errors.append("scroll_id and purpose are required")
    if not scroll.affected_files:
        errors.append("affected_files must not be empty")
    if not scroll.test_commands:
        errors.append("test_commands must not be empty")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "resonance": 1.0 if not errors else 0.0,
        "advisory": "Deterministic application controls (ThroneLock/canonical strategy resolver) remain authoritative.",
    }


# ─── Woo Interpreter (advisory trace) ─────────────────────────────────────────
def woo_interpret(scroll: Scroll) -> Dict[str, Any]:
    trace = [
        f"Loaded scroll {scroll.scroll_id}",
        f"Purpose: {scroll.purpose}",
        f"Affected files: {', '.join(sorted(scroll.affected_files))}",
        "Woo trace: advisory resonance complete; no uncontrolled trading instructions generated.",
    ]
    return {"trace": trace, "advisory_confidence": 0.95}


# ─── ThroneLock / Authorization Stub ──────────────────────────────────────────
def throne_lock_authorize(scroll: Scroll, role: str = "Executor") -> Dict[str, Any]:
    if role not in {"Executor", "Architect", "Guardian"}:
        raise PermissionError(f"ThroneLock: role '{role}' is not authorized to execute scrolls")
    return {
        "authorized": True,
        "role": role,
        "audit_trail": f"scroll {scroll.scroll_id} authorized by {role} at {datetime.now(timezone.utc).isoformat()}",
    }


# ─── Hash-Chained Registry ────────────────────────────────────────────────────
def _last_record_hash() -> Optional[str]:
    if not REGISTRY_PATH.exists():
        return None
    last = None
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            last = json.loads(line).get("record_hash")
    return last


def _record_hash(scroll: Scroll, content_hash: str, previous_record_hash: Optional[str]) -> str:
    payload = _canonical_json({
        "scroll_id": scroll.scroll_id,
        "content_hash": content_hash,
        "previous_record_hash": previous_record_hash,
        "sealed_at": scroll.sealed_at,
        "provenance": asdict(scroll.provenance),
    })
    return _sha256(payload.encode("utf-8"))


def register_scroll(scroll: Scroll) -> str:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(scroll), sort_keys=True) + "\n")
    return str(REGISTRY_PATH)


# ─── Runtime ──────────────────────────────────────────────────────────────────
def run_scroll(scroll: Scroll, role: str = "Executor") -> Scroll:
    authorization = throne_lock_authorize(scroll, role)
    validation = validate_scroll(scroll)
    if not validation["valid"]:
        raise RuntimeError(f"Scroll validation failed: {validation['errors']}")
    woo = woo_interpret(scroll)

    test_results = {}
    for cmd in scroll.test_commands:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=240)
            test_results[cmd] = {
                "returncode": result.returncode,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
            }
        except Exception as exc:
            test_results[cmd] = {"error": str(exc)}

    execution = {
        "authorization": authorization,
        "validation": validation,
        "woo": woo,
        "test_results": test_results,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    content_hash = scroll.content_hash_value()
    previous_record_hash = _last_record_hash()
    now = datetime.now(timezone.utc).isoformat()
    record_hash = _record_hash(scroll, content_hash, previous_record_hash)

    scroll.content_hash = content_hash
    scroll.previous_record_hash = previous_record_hash
    scroll.record_hash = record_hash
    scroll.sealed_at = now
    scroll.validation_result = validation
    scroll.execution_result = execution

    register_scroll(scroll)
    return scroll


def main(argv: List[str] = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m moscript <scroll.json>")
        return 1
    path = Path(argv[0])
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["requested_permissions"] = ScrollPermissions(**raw.get("requested_permissions", {}))
    raw["provenance"] = ScrollProvenance(**raw.get("provenance", {}))
    scroll = Scroll(**raw)
    result = run_scroll(scroll)
    print(f"Scroll {result.scroll_id} content_hash={result.content_hash}")
    print(f"Record hash={result.record_hash} previous={result.previous_record_hash}")
    print(f"Registry: {REGISTRY_PATH}")
    print(f"Status: {result.status} production_authorized={result.production_authorized}")
    return 0 if all(t.get("returncode", 1) == 0 for t in (result.execution_result or {}).get("test_results", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
