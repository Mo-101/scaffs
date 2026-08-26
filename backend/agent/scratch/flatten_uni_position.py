import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client, BinanceFuturesConfig

client = get_binance_futures_client(BinanceFuturesConfig.from_env())
positions = client.get_positions(symbol="UNIUSDT")
print("Open UNIUSDT positions:", positions)
for p in positions:
    amt = float(p.get("positionAmt", 0.0))
    if amt != 0:
        print(f"Flattening position {amt} UNIUSDT...")
        flatten_res = client.place_order(
            symbol="UNIUSDT",
            side="SELL" if amt > 0 else "BUY",
            order_type="MARKET",
            quantity=abs(amt),
            reduce_only=True,
        )
        print("Flatten result:", flatten_res)

bal = client.get_account_balance()
print("\nAccount USDT Balance:", bal.get("USDT", {}))
