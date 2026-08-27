# Binance Futures Testnet / UI Reference Archive

This document archives the Binance Futures trading parameters, TP/SL ROI behavior, and reduce-only risk controls shared by the user for the Scaffs trading system.

## 1. TP/SL by ROI% (Binance UI behavior)

Binance allows setting TP/SL for an entire position using **ROI%**, **PnL**, or **Offset%**. The UI converts the ROI% into an absolute trigger price before the conditional order is placed.

### 1.1 Real example from Binance UI

- Symbol: `STXUSDT Perpetual`
- Side: `Long 5x`
- Entry Price: `0.2754 USDT`
- Mark Price: `0.2591 USDT`
- Take Profit: `0.3249` (`+90%` ROI)
- Stop Loss: `0.2588` (`-30%` ROI)
- Estimated PnL at TP: `+18.01 USDT`
- Estimated PnL at SL: `-6.04 USDT`
- Price Protection: enabled

### 1.2 Formula

For a **LONG** position:

```text
tp_price = entry × (1 + (tp_roi_pct / 100) / leverage)
sl_price = entry × (1 - (|sl_roi_pct| / 100) / leverage)
```

For a **SHORT** position:

```text
tp_price = entry × (1 - (tp_roi_pct / 100) / leverage)
sl_price = entry × (1 + (|sl_roi_pct| / 100) / leverage)
```

Estimated PnL:

```text
pnl = (roi_pct / 100) × (position_value / leverage)
```

### 1.3 Price protection

Binance's `Price Protection` can ignore a triggered TP/SL if the gap between `Last Price` and `Mark Price` exceeds a symbol-specific threshold. This maps to the `priceProtect` parameter on conditional orders.

---

## 2. USD-M Futures trading parameters (examples)

| Symbol | Min. Trade Amount | Min. Order Price / Min. Price Movement | Price Precision | Limit Order Price Cap / Floor Ratio | Max. Market / Limit Order Amount | Max. Open Orders | Price Protection Threshold | Liquidation Clearance Fee | Min. Notional | Market Order Price Cap/Floor |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | 0.001 BTC | 556.80 / 0.10 USDT | 0.01 | 5% / 5% | 120 / 1000 BTC | 200 | 5% | 1.25% | 50 USDT | 5% |
| ETHUSDT | 0.001 ETH | 39.86 / 0.01 USDT | 0.01 | 5% / 5% | 2000 / 10000 ETH | 200 | 5% | 1.25% | 20 USDT | 5% |
| BCHUSDT | 0.001 BCH | 4 / 0.01 USDT | 0.01 | 5% / 5% | 2000 / 20000 BCH | 200 | 5% | 1.25% | 20 USDT | 5% |
| XRPUSDT | 0.1 XRP | 0.0143 / 0.0001 USDT | 0.0001 | 5% / 5% | 2000000 / 10000000 XRP | 200 | 5% | 1.25% | 5 USDT | 5% |
| LTCUSDT | 0.001 LTC | 0.01 / 0.01 USDT | 0.01 | 5% / 5% | 5000 / 20000 LTC | 200 | 5% | 1.25% | 20 USDT | 5% |
| TRXUSDT | 1 TRX | 0.00132 / 0.00001 USDT | 0.00001 | 5% / 5% | 5000000 / 20000000 TRX | 200 | 5% | 1.25% | 5 USDT | 5% |
| ETCUSDT | 0.01 ETC | 0.001 / 0.001 USDT | 0.001 | 10% / 10% | 40000 / 400000 ETC | 200 | 10% | 1.25% | 20 USDT | 10% |
| LINKUSDT | 0.01 LINK | 0.001 / 0.001 USDT | 0.001 | 10% / 10% | 50000 / 700000 LINK | 200 | 10% | 1.25% | 20 USDT | 10% |
| XLMUSDT | 1 XLM | 0.00648 / 0.00001 USDT | 0.00001 | 5% / 5% | 2000000 / 10000000 XLM | 200 | 5% | 1.25% | 5 USDT | 5% |
| ADAUSDT | 1 ADA | 0.00010 / 0.00010 USDT | 0.00001 | 5% / 5% | 3000000 / 30000000 ADA | 200 | 5% | 1.25% | 5 USDT | 5% |
| XMRUSDT | 0.001 XMR | 4.36 / 0.01 USDT | 0.01 | 5% / 5% | 1200 / 5000 XMR | 200 | 5% | 2.00% | 5 USDT | 5% |
| DASHUSDT | 0.001 DASH | 0.01 / 0.01 USDT | 0.01 | 10% / 10% | 3000 / 30000 DASH | 200 | 10% | 1.50% | 5 USDT | 10% |

### 2.1 Margin formula

```text
Initial Margin = Position Value / Leverage
Maintenance Margin = Position Value × Maintenance Margin Rate - Maintenance Amount
```

### 2.2 BTCUSDT Perpetual leverage brackets

| Tier | Position Bracket (USDT) | Max Leverage | Maintenance Margin Rate | Maintenance Amount (USDT) |
|---|---:|---:|---:|---:|
| 1 | 0 - 300,000 | 150x | 0.40% | 0 |
| 2 | 300,000 - 800,000 | 100x | 0.50% | 300 |
| 3 | 800,000 - 3,000,000 | 75x | 0.65% | 1,500 |
| 4 | 3,000,000 - 12,000,000 | 50x | 1.00% | 12,000 |
| 5 | 12,000,000 - 70,000,000 | 25x | 2.00% | 132,000 |

> Binance may adjust max leverage, position brackets, and maintenance margin rates during extreme price movements.

---

## 3. Reduce-only trigger conditions

### 3.1 For one single account

Conditions for "Reduce Only" trading restrictions are set by a risk control schedule, consisting of:

- The trading position size of a contract
- The ratio of the position size in relation to the size of the contract
- The gap between the position's liquidation price and the mark price

| Symbol | Open Position Notional Value Threshold | Position-to-Total-Position Ratio Threshold | Liquidation-Mark Price Gap Threshold |
|---|---:|---:|---:|
| BTCUSDT perpetual | 200,000,000 | 50% | 25% |
| ETHUSDT perpetual | 200,000,000 | 50% | 15% |
| BCHUSDT perpetual | 2,000,000 | 5% | 25% |
| XRPUSDT perpetual | 2,000,000 | 5% | 25% |
| LTCUSDT perpetual | 2,000,000 | 5% | 25% |
| TRXUSDT perpetual | 1,000,000 | 2% | 25% |
| ETCUSDT perpetual | 1,000,000 | 5% | 25% |
| LINKUSDT perpetual | 1,000,000 | 5% | 25% |
| XLMUSDT perpetual | 1,000,000 | 5% | 25% |
| ADAUSDT perpetual | 1,000,000 | 5% | 25% |

### 3.2 For one single user (including sub-accounts)

If the total position size of one user (main + sub-accounts) exceeds the notional-value threshold, or the user's Total Position Size / Open Interest exceeds the percentage threshold, the user's main account and sub-accounts will trigger a **reduce-only** risk limit.

| Symbol | Notional Value Threshold | Open Interest Percentage |
|---|---:|---:|
| BTCUSDT perpetual | 1,000,000,000 | 15% |
| ETHUSDT perpetual | 900,000,000 | 15% |
| BCHUSDT perpetual | 40,000,000 | 20% |
| XRPUSDT perpetual | 200,000,000 | 20% |
| LTCUSDT perpetual | 10,000,000 | 20% |
| TRXUSDT perpetual | 30,000,000 | 22.5% |
| ETCUSDT perpetual | 10,000,000 | 25% |
| LINKUSDT perpetual | 27,000,000 | 25% |
| XLMUSDT perpetual | 20,000,000 | 22.5% |
| ADAUSDT perpetual | 31,000,000 | 22.5% |
| XMRUSDT perpetual | 3,500,000 | 27.5% |
| DASHUSDT perpetual | 2,000,000 | 30% |
| ZECUSDT perpetual | 80,000,000 | 20% |
| XTZUSDT perpetual | 2,750,000 | 25% |
| BNBUSDT perpetual | 100,000,000 | 20% |
| ATOMUSDT perpetual | 11,000,000 | 25% |
| ONTUSDT perpetual | 1,250,000 | 27.5% |
| IOTAUSDT perpetual | 3,000,000 | 30% |
| BATUSDT perpetual | 1,500,000 | 35% |
| VETUSDT perpetual | 5,500,000 | 35% |
| NEOUSDT perpetual | 3,500,000 | 27.5% |
| QTUMUSDT perpetual | 2,750,000 | 35% |
| IOSTUSDT perpetual | 2,500,000 | 37.5% |
| THETAUSDT perpetual | 3,500,000 | 27.5% |
| ALGOUSDT perpetual | 6,000,000 | 30% |
| ZILUSDT perpetual | 2,250,000 | 40% |
| KNCUSDT perpetual | 1,250,000 | 40% |
| ZRXUSDT perpetual | 2,000,000 | 35% |
| COMPUSDT perpetual | 8,000,000 | 22.5% |
| DOGEUSDT perpetual | 100,000,000 | 20% |

> Calculations are performed separately for long and short notional values. Either side exceeding its threshold will trigger reduce-only for the whole user.

---

## 4. Implications for Scaffs

- **ROI% TP/SL** should be stored in `criteria_vector` as `tp_roi_pct` / `sl_roi_pct` and converted to absolute prices at order time using the entry price and confirmed leverage.
- **Tick size / price precision** must be respected before calling `POST /fapi/v1/algoOrder`.
- **`priceProtect=true`** can be passed for assets with a 5% or 10% price protection threshold.
- **Reduce-only risk limits** are not a concern for the small Testnet positions currently in the account but must be considered if scaling up position size.
- **Margin mode** should remain `ISOLATED` as the default to avoid cross-margin liquidation cascading.
