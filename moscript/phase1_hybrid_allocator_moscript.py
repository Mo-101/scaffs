#!/usr/bin/env python3
"""
MoScript-style Phase 1 installer for Scaffs Hybrid Portfolio Allocator.

Usage:
    python phase1_hybrid_allocator_moscript.py /path/to/scaffs --dry-run
    python phase1_hybrid_allocator_moscript.py /path/to/scaffs --apply

It copies only new Phase-1 hybrid files. It intentionally DOES NOT rewrite
existing strategy engines because their exact source APIs must be inspected in
the target checkout before integration.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

THIS = Path(__file__).resolve().parent

COPY_PATHS = [
    Path("backend/agent/src/trading/hybrid"),
    Path("backend/agent/tests/test_hybrid_phase1.py"),
    Path("migrations/001_hybrid_phase1.sql"),
]

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    repo = args.repo.resolve()
    if not repo.exists():
        raise SystemExit(f"repo does not exist: {repo}")

    print("Scaffs Hybrid Phase 1")
    print("repo:", repo)
    print("mode:", "DRY RUN" if args.dry_run else "APPLY")
    print()

    for rel in COPY_PATHS:
        src = THIS / rel
        dst = repo / rel
        print(f"{src} -> {dst}")
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                if dst.exists():
                    raise SystemExit(
                        f"refusing to overwrite existing directory: {dst}\n"
                        "Inspect/merge manually to preserve current execution behavior."
                    )
                shutil.copytree(src, dst)
            else:
                if dst.exists():
                    raise SystemExit(f"refusing to overwrite existing file: {dst}")
                shutil.copy2(src, dst)

    if args.apply:
        print("\nInstalled new Phase-1 files only.")
        print("Next: inspect engine APIs and add adapter calls one engine at a time.")
        print("Do NOT enable allocator execution in Phase 1.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
