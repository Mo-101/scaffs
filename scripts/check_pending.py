#!/usr/bin/env python3
"""Check all pending signals, classic limit orders, and conditional algo orders."""

import os
import sys
import json
import psycopg
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "backend" / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

os.environ["POSTGRES_HOST_PORT"] = os.getenv("POSTGRES_HOST_PORT", "5434")

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

def main():
    client = get_binance_futures_client()
    symbols = ["BTCUSDT", "SOLUSDT", "TAOUSDT", "ETHUSDT", "BNBUSDT"]

    print("==========================================")
    print("=== 1. PENDING SIGNALS IN POSTGRES QUEUE ===")
    print("==========================================")
    try:
        with psycopg.connect("postgresql://postgres:mostar@127.0.0.1:5434/mostar") as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, symbol, side, status, producer, raw_score, created_at 
                FROM paper_trading.signal_queue 
                WHERE status = 'PENDING' 
                ORDER BY created_at DESC;
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r["id"] = str(r["id"])
                r["created_at"] = str(r["created_at"])
            print(f"Pending Signal Queue Count: {len(rows)}")
            if rows:
                print(json.dumps(rows, indent=2, cls=DecimalEncoder))
    except Exception as e:
        print("Postgres DB Error:", e)

    print("\n==========================================")
    print("=== 2. PENDING CLASSIC LIMIT ORDERS ON BINANCE ===")
    print("==========================================")
    has_classic = False
    for sym in symbols:
        orders = client.get_open_orders(sym)
        if orders:
            has_classic = True
            for o in orders:
                print(f"[{sym}] Order ID: {o['orderId']} | Type: {o['type']} | Side: {o['side']} | Price: {o['price']} | Qty: {o['origQty']} | Status: {o['status']}")
    if not has_classic:
        print("No pending classic limit orders currently resting on exchange.")

    print("\n==========================================")
    print("=== 3. PENDING CONDITIONAL ALGO ORDERS (SL / TP) ===")
    print("==========================================")
    has_algos = False
    for sym in symbols:
        algos = client.get_open_algo_orders(sym)
        if algos:
            has_algos = True
            for a in algos:
                print(f"[{sym}] Algo ID: {a['algoId']} | Type: {a['orderType']} | Side: {a['side']} | TriggerPrice: ${a['triggerPrice']} | Status: {a['algoStatus']} | ClientAlgoId: {a['clientAlgoId']}")
    if not has_algos:
        print("No pending conditional algo orders.")

if __name__ == "__main__":
    main()
