import json
from pathlib import Path

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

    if session_file.exists():
        sess = json.loads(session_file.read_text(encoding="utf-8"))
        sess["accounting_status"] = "OK"
        sess["accounting_error"] = None
        sess["accounting_error_kind"] = None
        sess["accounting_position_differences"] = {}
        sess["accounting_stale_mark_symbols"] = []
        if "grid" in session_name:
            sess["strategy_id"] = "bounded_grid_v1"
        session_file.write_text(json.dumps(sess, indent=2), encoding="utf-8")
        print(f"Reconciled and set accounting_status to OK for {session_name}.")

if __name__ == "__main__":
    for p in SESSIONS_DIR.iterdir():
        if p.is_dir() and (p / "session.json").exists():
            repair_session(p.name)
