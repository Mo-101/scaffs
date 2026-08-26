import sys
from dotenv import load_dotenv
load_dotenv("/home/idona/MoStar/scaffs/.env")
sys.path.insert(0, "/home/idona/MoStar/scaffs/backend/agent")
from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

client = get_binance_futures_client()
positions = client.get_positions()
balances = client.get_account_balance()

print("================================================================================")
print("FINAL TESTNET AUDIT AFTER ROUND-TRIP")
print("================================================================================")
for b in balances:
    if b.get("asset") == "USDT":
        print(f"USDT Balance: {b.get('balance')} (Available: {b.get('availableBalance')})")

print("\nOpen Positions:")
open_pos = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
if not open_pos:
    print("  All positions FLAT (0 open positions).")
else:
    for p in open_pos:
        print(f"  {p.get('symbol')}: amt={p.get('positionAmt')}, entryPrice={p.get('entryPrice')}, unRealizedProfit={p.get('unRealizedProfit')}")
print("================================================================================")
