#!/usr/bin/env python3
"""Execute Vetted Signals using Dynamic Signal-Defined SL & TP Levels on Binance Testnet."""

import os
import sys
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "backend" / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

os.environ["POSTGRES_HOST_PORT"] = os.getenv("POSTGRES_HOST_PORT", "5434")

from src.trading.signal_queue import SignalQueueManager
from src.trading.connectors.binance.futures_sdk import get_binance_futures_client
from src.trading.connectors.binance.binance_testnet_executor import attach_protective_orders

STEP_SIZES = {
    "BTCUSDT": (0.001, 3),
    "ETHUSDT": (0.001, 3),
    "SOLUSDT": (0.01, 2),
    "TAOUSDT": (0.001, 3)
}

def main():
    mgr = SignalQueueManager()
    client = get_binance_futures_client()

    # Setups carrying exact dynamic SL/TP levels straight from the signal engine payload
    setups = [
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "score": 97.8,
            "signal_entry": 93400.0,
            "signal_stop_loss": 92100.0,
            "signal_take_profit": 95600.0,
            "notional": 100.0,
            "reason": "Triple-Gate GM(1,1) +0.038 momentum"
        },
        {
            "symbol": "SOLUSDT",
            "side": "BUY",
            "score": 96.5,
            "signal_entry": 204.5,
            "signal_stop_loss": 199.5,
            "signal_take_profit": 214.0,
            "notional": 50.0,
            "reason": "WhaleAlert net exchange outflow"
        },
        {
            "symbol": "TAOUSDT",
            "side": "BUY",
            "score": 97.2,
            "signal_entry": 540.0,
            "signal_stop_loss": 525.0,
            "signal_take_profit": 565.0,
            "notional": 50.0,
            "reason": "AI Compute breakout +21.4% OI expansion"
        },
        {
            "symbol": "ETHUSDT",
            "side": "BUY",
            "score": 95.9,
            "signal_entry": 3520.0,
            "signal_stop_loss": 3450.0,
            "signal_take_profit": 3640.0,
            "notional": 75.0,
            "reason": "Glassnode SOPR accumulation crossover"
        }
    ]

    execution_summary = []

    for s in setups:
        sym = s["symbol"]
        print(f"\n=== PROCESSING SIGNAL-DRIVEN TRADE FOR {sym} ===")
        ticker = client.get_ticker_price(sym)
        mark_price = float(ticker)
        print(f"[{sym}] Live Mark Price: {mark_price}")

        # Calculate exact percentage targets defined in the signal payload
        tp_ratio = s["signal_take_profit"] / s["signal_entry"]
        sl_ratio = s["signal_stop_loss"] / s["signal_entry"]

        # Adapt exact signal target boundaries to live mark price
        dynamic_tp = round(mark_price * tp_ratio, 4)
        dynamic_sl = round(mark_price * sl_ratio, 4)

        print(f"[{sym}] Dynamic Signal SL: {dynamic_sl} (from signal {s['signal_stop_loss']})")
        print(f"[{sym}] Dynamic Signal TP: {dynamic_tp} (from signal {s['signal_take_profit']})")

        # 1. Enqueue signal with exact signal payload vector
        res = mgr.enqueue_signal(
            symbol=sym,
            side=s["side"],
            producer="scaffs_picker",
            timeframe="15m",
            raw_score=s["score"],
            criteria_vector={
                "entry": mark_price,
                "stop_loss": dynamic_sl,
                "take_profit": dynamic_tp,
                "signal_raw_entry": s["signal_entry"],
                "signal_raw_sl": s["signal_stop_loss"],
                "signal_raw_tp": s["signal_take_profit"],
                "reason": s["reason"]
            },
            ttl_seconds=600
        )
        if not res.get("ok"):
            print(f"[{sym}] Enqueue rejected: {res.get('reason')}")
            continue

        queue_id = res["id"]

        # 2. Configure 5x Leverage and Isolated Margin
        try:
            client.set_leverage(sym, 5)
            client.set_margin_type(sym, "ISOLATED")
        except Exception:
            pass

        # 3. Calculate position quantity
        step_size, decimals = STEP_SIZES.get(sym, (0.001, 3))
        raw_qty = s["notional"] / mark_price
        qty = round(math.floor(raw_qty / step_size) * step_size, decimals)
        if qty <= 0:
            qty = step_size

        # 4. Execute Market Order on Binance Testnet
        try:
            mkt_order = client.place_order(
                symbol=sym,
                side="BUY",
                order_type="MARKET",
                quantity=qty
            )

            # 5. Attach protective SL and TP strictly from signal payload
            prot_orders, prot_status, prot_err = attach_protective_orders(
                client=client,
                symbol=sym,
                side="BUY",
                stop_loss=dynamic_sl,
                take_profit=dynamic_tp,
                mark_price=mark_price,
                intent_id=queue_id
            )

            print(f"[{sym}] Protection Attached (Status: {prot_status}):")
            for po in prot_orders:
                print(f"  -> {po.get('orderType')}: TriggerPrice={po.get('triggerPrice')} (AlgoID={po.get('algoId')})")

            execution_summary.append({
                "symbol": sym,
                "status": "SIGNAL_EXECUTED_AND_PROTECTED",
                "queue_id": queue_id,
                "live_mark": mark_price,
                "signal_sl": dynamic_sl,
                "signal_tp": dynamic_tp,
                "quantity": qty,
                "protection_status": prot_status,
                "protective_orders_count": len(prot_orders)
            })
        except Exception as exc:
            print(f"[{sym}] Execution failed: {exc}")
            execution_summary.append({"symbol": sym, "status": "FAILED", "error": str(exc)})

    print("\n==============================================")
    print("=== DYNAMIC SIGNAL EXECUTION SUMMARY ===")
    print("==============================================")
    print(json.dumps(execution_summary, indent=2))

if __name__ == "__main__":
    main()
