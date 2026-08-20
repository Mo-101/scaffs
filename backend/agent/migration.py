import json
import shutil
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

def reconstruct_state(session_dir: Path) -> Optional[dict[str, Any]]:
    # Load session_config.json to get initial_balance
    config_path = session_dir / "session_config.json"
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
        
    initial_balance = float(config.get("initial_balance", 10000.0))
    
    # Load trades.jsonl
    trades_path = session_dir / "trades.jsonl"
    trades = []
    if trades_path.exists():
        try:
            with open(trades_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except Exception:
            return None
            
    # Load account.json to get open positions
    account_path = session_dir / "account.json"
    if not account_path.exists():
        return None
    try:
        legacy_account = json.loads(account_path.read_text(encoding="utf-8"))
    except Exception:
        return None
        
    # Reconstruct metrics
    closed_trades_count = len(trades)
    realized_gross = sum(float(t.get("gross_pnl", 0.0)) for t in trades)
    realized_net = sum(float(t.get("net_pnl", 0.0)) for t in trades)
    closed_fees = sum(float(t.get("entry_fee", 0.0)) + float(t.get("exit_fee", 0.0)) for t in trades)
    closed_funding = sum(float(t.get("funding_paid", 0.0)) for t in trades)
    closed_liq_fees = sum(float(t.get("liquidation_fee", 0.0)) for t in trades)
    
    # Open positions
    open_positions = legacy_account.get("positions", {})
    open_fees = sum(float(p.get("entry_fee", 0.0)) for p in open_positions.values())
    open_funding = sum(float(p.get("accrued_funding", 0.0)) for p in open_positions.values())
    open_margin = sum(float(p.get("isolated_margin", 0.0)) for p in open_positions.values())
    open_notional = sum(float(p.get("notional", 0.0)) for p in open_positions.values())
    
    total_fees = closed_fees + open_fees
    total_funding = closed_funding + open_funding
    total_liq_fees = closed_liq_fees
    
    wallet_balance = initial_balance + realized_gross - total_fees - total_funding - total_liq_fees
    
    reconstructed = {
        "schema_version": 2,
        "initial_balance": initial_balance,
        "wallet_balance": wallet_balance,
        "reserved_margin": open_margin,
        "realized_gross_pnl": realized_gross,
        "realized_net_pnl": realized_net,
        "total_fees": total_fees,
        "total_funding": total_funding,
        "total_liquidation_fees": total_liq_fees,
        "opened_trades": closed_trades_count + len(open_positions),
        "closed_trades": closed_trades_count,
        "open_notional": open_notional,
        "positions": open_positions,
        "status": legacy_account.get("status", "OK"),
        "analytics_version": 2,
        "analytics_source": "closed_trade_ledger",
        "reconstructed_at": datetime.now(timezone.utc).isoformat(),
        "applied_funding_event_ids": legacy_account.get("applied_funding_event_ids", []),
        "last_txn_id": legacy_account.get("last_txn_id", ""),
        "committed_txn_ids": legacy_account.get("committed_txn_ids", []),
        "total_insurance_fund_shortfall": float(legacy_account.get("total_insurance_fund_shortfall", 0.0)),
        "updated_at": legacy_account.get("updated_at", datetime.now(timezone.utc).isoformat()),
    }
    
    # Check if the reconstructed values match the legacy values
    epsilon = 1e-4
    match = True
    for key in ["wallet_balance", "reserved_margin", "realized_net_pnl", "total_fees", "total_funding", "open_notional"]:
        if key in legacy_account:
            val_legacy = float(legacy_account[key])
            val_recon = reconstructed[key]
            if abs(val_recon - val_legacy) > epsilon:
                match = False
                break
                
    if not match:
        return None
        
    return reconstructed

def reconstruct_and_migrate_session(session_dir: Path) -> str:
    # Check if this session is already migrated (has analytics_version: 2)
    account_path = session_dir / "account.json"
    if not account_path.exists():
        return "NO_ACCOUNT"
        
    try:
        account_data = json.loads(account_path.read_text(encoding="utf-8"))
        if account_data.get("analytics_version") == 2:
            return "ALREADY_MIGRATED"
    except Exception:
        pass
        
    reconstructed = reconstruct_state(session_dir)
    if reconstructed is not None:
        try:
            account_path.write_text(json.dumps(reconstructed, indent=2), encoding="utf-8")
            return "MIGRATED"
        except Exception:
            return "WRITE_FAILED"
    else:
        try:
            quarantine_path = session_dir / "account.json.quarantine"
            if account_path.exists():
                shutil.copy2(account_path, quarantine_path)
            
            unreconciled_state = {
                "status": "LEGACY_UNRECONCILED",
                "analytics_version": 2,
                "analytics_source": "closed_trade_ledger",
                "reconstructed_at": datetime.now(timezone.utc).isoformat(),
                "error": "reconstruction failed",
            }
            account_path.write_text(json.dumps(unreconciled_state, indent=2), encoding="utf-8")
            return "QUARANTINED"
        except Exception:
            return "QUARANTINE_FAILED"

def migrate_all_sessions(sessions_dir: Path) -> dict[str, str]:
    results = {}
    if not sessions_dir.exists():
        return results
    for sub in sessions_dir.iterdir():
        if sub.is_dir() and (sub / "account.json").exists():
            results[sub.name] = reconstruct_and_migrate_session(sub)
    return results
