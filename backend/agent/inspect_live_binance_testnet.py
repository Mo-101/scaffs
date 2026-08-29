import sys
from pathlib import Path
agent_dir = Path(__file__).resolve().parent
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

def main():
    c = get_binance_futures_client()
    print("=== LIVE BINANCE TESTNET POSITIONS ===")
    positions = c.get_positions()
    for p in positions:
        amt = float(p.get("positionAmt", 0))
        if amt != 0:
            print(f"Symbol: {p.get('symbol')}, Amt: {amt}, EntryPrice: {p.get('entryPrice')}, Leverage: {p.get('leverage')}, MarginType: {p.get('marginType')}")

    print("\n=== LIVE OPEN ORDERS & ALGO ORDERS ===")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]:
        classic = c.get_open_orders(sym)
        if classic:
            print(f"{sym} Classic Open Orders: {classic}")
        algos = c.get_open_algo_orders(sym)
        if algos:
            print(f"{sym} Open Algo Orders: {algos}")

if __name__ == "__main__":
    main()
