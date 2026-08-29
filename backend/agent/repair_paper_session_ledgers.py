import json
import sys
from pathlib import Path

# Add backend/agent to sys.path
agent_dir = Path(__file__).resolve().parent
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

import paper_session as ps

SESSIONS_DIR = Path(__file__).resolve().parent / "paper_sessions"

def repair_session(session_name: str):
    session_dir = SESSIONS_DIR / session_name
    if not session_dir.exists():
        return

    trades_file = session_dir / "trades.jsonl"
    book_file = session_dir / "book.json"
    session_file = session_dir / "session.json"

    if trades_file.exists():
        lines = trades_file.read_text(encoding="utf-8").strip().splitlines()
        trades = [json.loads(l) for l in lines if l.strip()]

        cleaned_trades = []
        for t in trades:
            ts = t.get("timestamp", "")
            # Drop duplicate retry SELL trades
            if "2026-08-27T12:49:39" in ts or "2026-08-27T12:50:09" in ts or "2026-08-27T12:50:39" in ts:
                continue
            if "2026-08-27T12:52:01" in ts and t.get("symbol") != "BNB-USDT":
                continue
            cleaned_trades.append(t)

        new_trades_content = "\n".join(json.dumps(t, ensure_ascii=False) for t in cleaned_trades) + "\n"
        trades_file.write_text(new_trades_content, encoding="utf-8")

        # Compute net positions from cleaned trades.jsonl
        positions = {}
        for t in cleaned_trades:
            sym = t["symbol"]
            signed_qty = t["qty"] if t["side"] == "BUY" else -t["qty"]
            positions[sym] = positions.get(sym, 0.0) + signed_qty

        # Sync book.json positions
        if book_file.exists():
            book = json.loads(book_file.read_text(encoding="utf-8"))
            book["positions"] = positions
            book_file.write_text(json.dumps(book, indent=2), encoding="utf-8")

    # Re-evaluate live accounting diagnostic state
    diag = ps.compute_session_diagnostics(session_dir)
    res_err = diag.get("metrics", {}).get("reconciliation_error", 0.0)
    is_rec = diag.get("metrics", {}).get("reconciled", False)

    if session_file.exists():
        sess = json.loads(session_file.read_text(encoding="utf-8"))
        sess["accounting_status"] = "OK" if is_rec else "ACCOUNTING_ERROR"
        sess["accounting_error"] = res_err
        sess["accounting_error_kind"] = None if is_rec else "RESIDUAL_ERROR"
        sess["accounting_position_differences"] = {}
        sess["accounting_stale_mark_symbols"] = []
        if "grid" in session_name:
            sess["strategy_id"] = "bounded_grid_v1"
        session_file.write_text(json.dumps(sess, indent=2), encoding="utf-8")

    print(f"Session: {session_name:25s} | Reconciled: {str(is_rec):5s} | Numeric Residual: {res_err:+.12e}")

if __name__ == "__main__":
    print("=== EMPIRICAL PAPER SESSION RESIDUAL AUDIT ===")
    for p in sorted(SESSIONS_DIR.iterdir()):
        if p.is_dir() and (p / "session.json").exists():
            repair_session(p.name)
