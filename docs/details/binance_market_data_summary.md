# Binance Futures Market Data Summary (Archive)

This file captures the funding rates, order limits, multi-asset margin rules, and leverage schedules shared by the user for the Scaffs trading system.

## 1. Funding rates (8h interval)

| Symbol | Interval | Next Funding | Interest Rate | Last Funding Rate | Funding Cap / Floor |
|---|---|---|---|---|---|
| BTCUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.3000% / -0.3000% |
| BNBUSDT Perpetual | 8h | 06:41:45 | 0.00343% | 0.0000% | 0.3750% / -0.3750% |
| ETHUSDT Perpetual | 8h | 06:41:45 | 0.00877% | 0.0100% | 0.3000% / -0.3000% |
| BCHUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.3750% / -0.3750% |
| XRPUSDT Perpetual | 8h | 06:41:45 | 0.00464% | 0.0100% | 0.3750% / -0.3750% |
| LTCUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.3750% / -0.3750% |
| TRXUSDT Perpetual | 8h | 06:41:45 | -0.00221% | 0.0100% | 0.4875% / -0.4875% |
| ETCUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 2.0000% / -2.0000% |
| LINKUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.3750% / -0.3750% |
| XLMUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.7500% / -0.7500% |
| ADAUSDT Perpetual | 8h | 06:41:45 | 0.00093% | 0.0100% | 0.3750% / -0.3750% |
| XMRUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 0.7500% / -0.7500% |
| DASHUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 2.0000% / -2.0000% |
| ZECUSDT Perpetual | 8h | 06:41:45 | 0.01000% | 0.0100% | 2.0000% / -2.0000% |
| XTZUSDT Perpetual | 4h | 02:41:45 | 0.00500% | 0.0100% | 2.0000% / -2.0000% |

## 2. Conditional / open order limits

```text
Conditional orders across all symbols: 200 open orders per user
Regular Stop Limit, Stop Market, Trailing Stop: 10 open orders per symbol
Total regular orders across all symbols: 10,000 open orders
```

## 3. Multi-Assets Mode

### 3.1 Supported margin assets (sample)

| Asset | Collateral Value Ratio |
|---|---|
| BTC | 95.00% |
| BNB | 95.00% |
| ETH | 95.00% |
| USDT | 99.99% |
| USDC | 99.99% |
| FDUSD | 98.90% |
| BFUSD | 99.90% |
| LDUSDT | 99.90% |
| RWUSD | 99.90% |

> Haircuts apply: e.g., $1000 of BNB is valued at $950, $1000 of FDUSD at $989.

### 3.2 Auto-Exchange triggers

| Asset | Threshold (Regular & VIP1) | Haircut | Bid/Ask Buffer |
|---|---|---|---|
| USDT | -5,000 USDT | 0.01% | 0.01% |
| BTC | -0.1 BTC | 2.50% | 2.50% |
| BNB | 0 BNB | 5.00% | 5.00% |
| ETH | 0 ETH | 2.50% | 2.50% |
| USDC | -5,000 USDC | 0.01% | 0.01% |
| FDUSD | 0 FDUSD | 1.00% | 1.00% |
| BFUSD | 0 BFUSD | 0.10% | 0.10% |
| LDUSDT | 0 LDUSDT | 0.10% | 0.10% |
| RWUSD | 0 RWUSD | 0.10% | 0.10% |
| USD1 | -5,000 USD1 | 1.00% | 1.00% |
| U | -5,000 U | 1.00% | 1.00% |

Auto-Exchange happens when:
1. Wallet balance < threshold (or VIP2+ -10,000)
2. Liquidation occurs and balance cannot cover deficit
3. No positions or open orders and LTV ≥ 0.995

### 3.3 Multi-Assets exchange rates

| Pair | Ask Rate | Bid Rate | Index Price | Bid Buffer | Ask Buffer |
|---|---|---|---|---|---|
| USD1/USD | 1.0097 | 0.9897 | 0.9997 | 0.0100 | 0.0100 |
| BNB/USD | 747.7884 | 676.5705 | 712.1794 | 0.0500 | 0.0500 |
| LDUSDT/USD | 1.1358 | 1.1335 | 1.1347 | 0.0010 | 0.0010 |
| USDT/USD | 0.9999 | 0.9997 | 0.9998 | 0.0001 | 0.0001 |
| BTC/USD | 83988.3035 | 75989.4174 | 79988.8605 | 0.0500 | 0.0500 |
| FDUSD/USD | 1.0103 | 0.9883 | 0.9993 | 0.0110 | 0.0110 |
| U/USD | 1.0092 | 0.9892 | 0.9992 | 0.0100 | 0.0100 |
| ETH/USD | 2664.2323 | 2410.4959 | 2537.3641 | 0.0500 | 0.0500 |
| BFUSD/USD | 1.0008 | 0.9988 | 0.9998 | 0.0010 | 0.0010 |
| USDC/USD | 1.0000 | 0.9998 | 0.9999 | 0.0001 | 0.0001 |
| RWUSD/USD | 1.0009 | 0.9989 | 0.9999 | 0.0010 | 0.0010 |
| BNFCR/USD | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 |

## 4. Leverage & margin (selected / summary)

Binance provides per-asset leverage brackets. Examples:

### 4.1 BTCUSDT / ETHUSDT brackets (tiered)

| Tier | Notional Value (USDT) | Max Leverage | Maintenance Margin Rate |
|---|---:|---:|---:|
| 1 | 0 - 300,000 | 150x | 0.40% |
| 2 | 300,000 - 800,000 | 100x | 0.50% |
| 3 | 800,000 - 3,000,000 | 75x | 0.65% |
| 4 | 3,000,000 - 12,000,000 | 50x | 1.00% |
| 5 | 12,000,000 - 70,000,000 | 25x | 2.00% |

### 4.2 Margins commonly observed

```text
Initial Margin = Position Value / Leverage
Maintenance Margin = Position Value × Maintenance Margin Rate - Maintenance Amount
```

## 5. Notes for Scaffs

- Funding rates are paid/received every 8h (some symbols 4h). Long positions with negative funding earn; positive funding cost.
- Conditional orders are capped at 200 per user — the reconciler must not exceed this.
- Multi-Assets mode is not enabled for Scaffs; the system uses `ISOLATED` margin and `USDT` collateral by default.
- For live refreshes, use Binance endpoints:
  - `GET /fapi/v1/exchangeInfo` — filters, tick sizes, min notional
  - `GET /fapi/v1/fundingRate` — current/prev funding rates
  - `GET /fapi/v1/leverageBracket` — per-asset leverage tiers
