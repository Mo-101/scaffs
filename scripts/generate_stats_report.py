#!/usr/bin/env python3
"""Generate a complete system and trading stats report."""

import os
import sys
import json
import subprocess
import psycopg
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "backend" / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

os.environ["POSTGRES_HOST_PORT"] = os.getenv("POSTGRES_HOST_PORT", "5434")

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

def main():
    client = get_binance_futures_client()

    print("==========================================")
    print("=== 1. PM2 MICROSERVICES STATUS ===")
    print("==========================================")
    try:
        pm2_out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True).stdout
        pm2_data = json.loads(pm2_out)
        for p in pm2_data:
            pid = p["pm_id"]
            name = p["name"]
            status = p["pm2_env"]["status"]
            cpu = p["monit"]["cpu"]
            mem_mb = p["monit"]["memory"] // (1024 * 1024)
            print(f"[{pid}] {name:<22} | Status: {status:<8} | CPU: {cpu}% | Mem: {mem_mb}MB")
    except Exception as e:
        print("PM2 error:", e)

    print("\n==========================================")
    print("=== 2. SIGNAL QUEUE STATS (POSTGRES) ===")
    print("==========================================")
    try:
        with psycopg.connect("postgresql://postgres:mostar@127.0.0.1:5434/mostar") as conn, conn.cursor() as cur:
            cur.execute("SELECT status, count(*) FROM paper_trading.signal_queue GROUP BY status ORDER BY count DESC;")
            stats = dict(cur.fetchall())
            for status, count in stats.items():
                print(f"  -> {status:<28}: {count}")

            cur.execute("SELECT count(*) FROM paper_trading.signal_queue WHERE created_at > NOW() - INTERVAL '24 hours';")
            last_24h = cur.fetchone()[0]
            print(f"\nTotal Signals Enqueued in Last 24 Hours: {last_24h}")
    except Exception as e:
        print("Postgres Error:", e)

    print("\n==========================================")
    print("=== 3. BINANCE TESTNET COLLATERAL & POSITIONS ===")
    print("==========================================")
    try:
        bal = client.get_account_balance()
        usdt = next(b for b in bal if b["asset"] == "USDT")
        usdc = next(b for b in bal if b["asset"] == "USDC")
        btc = next(b for b in bal if b["asset"] == "BTC")

        print(f"USDT Total Balance     : ${float(usdt['balance']):,.2f}")
        print(f"USDT Available Balance : ${float(usdt['availableBalance']):,.2f}")
        print(f"USDT Cross UnPnL       : ${float(usdt['crossUnPnl']):,.2f}")
        print(f"USDC Total Balance     : ${float(usdc['balance']):,.2f}")
        print(f"BTC Total Balance      : {btc['balance']} BTC")

        positions = [p for p in client.get_positions() if float(p.get("positionAmt", 0)) != 0]
        print(f"\nActive Open Positions ({len(positions)} Total):")
        for p in positions:
            sym = p["symbol"]
            amt = float(p["positionAmt"])
            entry = float(p["entryPrice"])
            mark = float(p["markPrice"])
            pnl = float(p["unRealizedProfit"])
            pnl_pct = ((mark - entry) / entry * 100) if entry > 0 else 0.0
            print(f"  [{sym:<7}] Size: {amt:<6} | Entry: ${entry:<9.2f} | Mark: ${mark:<9.2f} | PnL: ${pnl:<+8.4f} ({pnl_pct:<+6.2f}%) | Lev: {p['leverage']}x")
    except Exception as e:
        print("Binance Error:", e)

    print("\n==========================================")
    print("=== 4. ACTIVE CONDITIONAL ALGO ORDERS (SL / TP) ===")
    print("==========================================")
    symbols = ["BTCUSDT", "SOLUSDT", "TAOUSDT", "ETHUSDT", "BNBUSDT"]
    total_algos = 0
    for sym in symbols:
        algos = client.get_open_algo_orders(sym)
        if algos:
            total_algos += len(algos)
            for a in algos:
                print(f"  [{sym:<7}] {a['orderType']:<18} ({a['side']:<4}) -> TriggerPrice: ${float(a['triggerPrice']):<9.2f} | AlgoID: {a['algoId']}")
    print(f"\nTotal Active Exchange Protective Algo Orders: {total_algos}")

if __name__ == "__main__":
    main()
