import os
import sys
from pathlib import Path

# Add backend/agent to sys.path
agent_dir = Path(__file__).resolve().parent
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from src.trading.connectors.binance.futures_sdk import get_binance_futures_client

def setup_binance_testnet():
    client = get_binance_futures_client()
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

    print("--- 1. Cancelling all open orders on Binance Testnet ---")
    for sym in symbols:
        try:
            res = client._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": sym}, signed=True)
            print(f"Cancelled classic open orders for {sym}: {res}")
        except Exception as e:
            print(f"Classic cancel for {sym}: {e}")

        try:
            # Cancel open algo orders if any
            open_algos = client._request("GET", "/fapi/v1/openAlgoOrders", params={"symbol": sym}, signed=True)
            if isinstance(open_algos, list):
                for algo in open_algos:
                    algo_id = algo.get("algoId")
                    if algo_id:
                        c_res = client.cancel_algo_order(symbol=sym, algo_id=algo_id)
                        print(f"Cancelled algo order {algo_id} for {sym}: {c_res}")
        except Exception as e:
            print(f"Algo cancel for {sym}: {e}")

    print("\n--- 2. Setting Margin Type to ISOLATED ---")
    for sym in symbols:
        try:
            res = client.set_margin_type(sym, "ISOLATED")
            print(f"Set ISOLATED margin for {sym}: {res}")
        except Exception as e:
            print(f"Set ISOLATED margin for {sym} response/note: {e}")

    print("\n--- 3. Setting Leverage to 5x ---")
    for sym in symbols:
        try:
            res = client.set_leverage(sym, 5)
            print(f"Set 5x leverage for {sym}: {res}")
        except Exception as e:
            print(f"Set leverage for {sym}: {e}")

    print("\n--- 4. Verifying Confirmed Exchange State ---")
    for sym in symbols:
        m_type = client.get_symbol_margin_type(sym)
        lev = client.get_symbol_leverage(sym)
        print(f"Symbol {sym}: MarginMode={m_type}, Leverage={lev}x")

if __name__ == "__main__":
    setup_binance_testnet()
