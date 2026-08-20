export interface PriceBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TradeMarker {
  time: string;
  side: "BUY" | "SELL";
  price: number;
  qty?: number;
  reason?: string;
}

export interface IndicatorPoint {
  time: string;
  value: number;
}

export interface RunDetail {
  run_id: string;
  status: string;
  prompt: string;
  created_at: string;
  elapsed_seconds: number;
  run_directory: string;
  metrics: {
    final_value: number;
    total_return: number;
    annual_return: number;
    max_drawdown: number;
    sharpe: number;
    win_rate: number;
    trade_count: number;
    profit_factor: number;
    sortino: number;
    calmar: number;
  };
  validation: {
    monte_carlo: {
      actual_sharpe: number;
      actual_max_dd: number;
      p_value_sharpe: number;
      p_value_max_dd: number;
      simulated_sharpe_mean: number;
      simulated_sharpe_std: number;
      simulated_sharpe_p5: number;
      simulated_sharpe_p95: number;
      n_simulations: 1000;
      n_trades: 48;
    };
    bootstrap: {
      observed_sharpe: number;
      ci_lower: number;
      ci_upper: number;
      median_sharpe: number;
      prob_positive: number;
      confidence: 0.95;
      n_bootstrap: 2000;
    };
    walk_forward: {
      n_windows: 5;
      windows: Array<{
        window: number;
        start: string;
        end: string;
        return: number;
        sharpe: number;
        max_dd: number;
        trades: number;
        win_rate: number;
      }>;
      profitable_windows: 4;
      consistency_rate: 0.8;
      return_mean: 0.245;
      return_std: 0.082;
      sharpe_mean: 1.84;
      sharpe_std: 0.42;
    };
  };
  chart_symbols: string[];
  price_series: Record<string, PriceBar[]>;
  indicator_series: Record<string, Record<string, IndicatorPoint[]>>;
  trade_markers: TradeMarker[];
  equity_curve: Array<{ time: string; equity: number; drawdown: number }>;
  trade_log: Array<Record<string, string>>;
  artifacts: Array<{
    name: string;
    path: string;
    type: string;
    size: number;
    exists: boolean;
  }>;
  pine_script: string;
  source_code: Record<string, string>;
}

export function generateRunData(
  runId: string,
  prompt: string,
  symbol: string = "BTC-USDT",
  days: number = 90
): RunDetail {
  const now = new Date();
  const bars: PriceBar[] = [];
  const rsi: IndicatorPoint[] = [];
  const macd: IndicatorPoint[] = [];
  const ma20: IndicatorPoint[] = [];
  const tradeMarkers: TradeMarker[] = [];
  const equityPoints: Array<{ time: string; equity: number; drawdown: number }> = [];

  let basePrice = symbol.includes("BTC") ? 64000 : symbol.includes("ETH") ? 2400 : 140;
  let equity = 100000;
  let peakEquity = 100000;
  let inPosition = false;
  let entryPrice = 0;

  for (let i = days; i >= 0; i--) {
    const t = new Date(now.getTime() - i * 24 * 3600 * 1000);
    const dateStr = t.toISOString().slice(0, 10);

    const change = (Math.random() - 0.485) * 0.035;
    const open = basePrice;
    const close = Number((open * (1 + change)).toFixed(2));
    const high = Number((Math.max(open, close) * (1 + Math.random() * 0.015)).toFixed(2));
    const low = Number((Math.min(open, close) * (1 - Math.random() * 0.015)).toFixed(2));
    const volume = Math.floor(10000 + Math.random() * 90000);
    basePrice = close;

    bars.push({ time: dateStr, open, high, low, close, volume });
    const rsiVal = 30 + Math.sin(i * 0.25) * 25 + Math.random() * 15;
    rsi.push({ time: dateStr, value: Number(rsiVal.toFixed(2)) });
    macd.push({ time: dateStr, value: Number((Math.sin(i * 0.15) * 2.5).toFixed(2)) });
    ma20.push({ time: dateStr, value: Number((close * (0.97 + Math.random() * 0.06)).toFixed(2)) });

    // Trading signals
    if (!inPosition && rsiVal < 38) {
      inPosition = true;
      entryPrice = close;
      tradeMarkers.push({
        time: dateStr,
        side: "BUY",
        price: close,
        qty: Number((equity * 0.5 / close).toFixed(4)),
        reason: "RSI Oversold + MA Bullish Divergence",
      });
    } else if (inPosition && (rsiVal > 68 || close < entryPrice * 0.95)) {
      inPosition = false;
      const profit = (close / entryPrice - 1) * (equity * 0.5);
      equity += profit;
      tradeMarkers.push({
        time: dateStr,
        side: "SELL",
        price: close,
        qty: Number((equity * 0.5 / close).toFixed(4)),
        reason: rsiVal > 68 ? "Take Profit RSI Exhaustion" : "Stop Loss Guard",
      });
    }

    if (equity > peakEquity) peakEquity = equity;
    const dd = ((equity - peakEquity) / peakEquity) * 100;
    equityPoints.push({
      time: dateStr,
      equity: Number(equity.toFixed(2)),
      drawdown: Number(dd.toFixed(2)),
    });
  }

  const totalReturn = (equity - 100000) / 100000;

  const pineScript = `//@version=5
strategy("${prompt.slice(0, 30).replace(/[^a-zA-Z0-9 ]/g, "")} Strategy", overlay=true, initial_capital=100000, default_qty_type=strategy.percent_of_equity, default_qty_value=50)

// Parameters
rsiLength = input.int(14, "RSI Length")
rsiOversold = input.int(38, "RSI Oversold")
rsiOverbought = input.int(68, "RSI Overbought")
fastLength = input.int(12, "MACD Fast")
slowLength = input.int(26, "MACD Slow")

// Calculations
rsiVal = ta.rsi(close, rsiLength)
[macdLine, signalLine, _] = ta.macd(close, fastLength, slowLength, 9)
ma20 = ta.sma(close, 20)

// Conditions
longCondition = ta.crossover(rsiVal, rsiOversold) and close > ma20
exitCondition = ta.crossunder(rsiVal, rsiOverbought) or (strategy.position_size > 0 and close < strategy.position_avg_price * 0.95)

// Order Execution
if (longCondition)
    strategy.entry("Long", strategy.long)

if (exitCondition)
    strategy.close("Long")

// Plotting
plot(ma20, "SMA 20", color=color.blue)
`;

  return {
    run_id: runId,
    status: "success",
    prompt,
    created_at: new Date(now.getTime() - 3600 * 1000).toISOString(),
    elapsed_seconds: 4.82,
    run_directory: `/runs/${runId}`,
    metrics: {
      final_value: Number(equity.toFixed(2)),
      total_return: Number(totalReturn.toFixed(4)),
      annual_return: Number((totalReturn * (365 / days)).toFixed(4)),
      max_drawdown: 0.084,
      sharpe: 2.14,
      win_rate: 0.68,
      trade_count: tradeMarkers.length,
      profit_factor: 2.45,
      sortino: 3.12,
      calmar: 2.85,
    },
    validation: {
      monte_carlo: {
        actual_sharpe: 2.14,
        actual_max_dd: 0.084,
        p_value_sharpe: 0.002,
        p_value_max_dd: 0.015,
        simulated_sharpe_mean: 1.95,
        simulated_sharpe_std: 0.28,
        simulated_sharpe_p5: 1.48,
        simulated_sharpe_p95: 2.42,
        n_simulations: 1000,
        n_trades: tradeMarkers.length,
      },
      bootstrap: {
        observed_sharpe: 2.14,
        ci_lower: 1.62,
        ci_upper: 2.68,
        median_sharpe: 2.11,
        prob_positive: 0.998,
        confidence: 0.95,
        n_bootstrap: 2000,
      },
      walk_forward: {
        n_windows: 5,
        windows: [
          { window: 1, start: "2024-01-01", end: "2024-03-01", return: 0.18, sharpe: 2.05, max_dd: 0.05, trades: 8, win_rate: 0.75 },
          { window: 2, start: "2024-03-01", end: "2024-05-01", return: 0.24, sharpe: 2.32, max_dd: 0.07, trades: 11, win_rate: 0.72 },
          { window: 3, start: "2024-05-01", end: "2024-07-01", return: -0.04, sharpe: -0.21, max_dd: 0.09, trades: 7, win_rate: 0.42 },
          { window: 4, start: "2024-07-01", end: "2024-09-01", return: 0.31, sharpe: 2.68, max_dd: 0.06, trades: 12, win_rate: 0.83 },
          { window: 5, start: "2024-09-01", end: "2024-11-01", return: 0.22, sharpe: 2.15, max_dd: 0.08, trades: 10, win_rate: 0.70 },
        ],
        profitable_windows: 4,
        consistency_rate: 0.8,
        return_mean: 0.182,
        return_std: 0.131,
        sharpe_mean: 1.798,
        sharpe_std: 1.13,
      },
    },
    chart_symbols: [symbol],
    price_series: {
      [symbol]: bars,
    },
    indicator_series: {
      [symbol]: {
        RSI: rsi,
        MACD: macd,
        SMA20: ma20,
      },
    },
    trade_markers: tradeMarkers,
    equity_curve: equityPoints,
    trade_log: tradeMarkers.map((m, idx) => ({
      index: String(idx + 1),
      time: m.time,
      side: m.side,
      price: String(m.price),
      reason: m.reason || "",
    })),
    artifacts: [
      { name: "backtest_results.json", path: `/runs/${runId}/backtest_results.json`, type: "json", size: 14280, exists: true },
      { name: "strategy.pine", path: `/runs/${runId}/strategy.pine`, type: "pine", size: pineScript.length, exists: true },
      { name: "equity_curve.csv", path: `/runs/${runId}/equity_curve.csv`, type: "csv", size: 8400, exists: true },
    ],
    pine_script: pineScript,
    source_code: {
      "strategy.py": `# Quantitative Strategy Generated by Vibe-Trading\nimport pandas as pd\nimport numpy as np\n\ndef generate_signals(df: pd.DataFrame) -> pd.Series:\n    rsi = compute_rsi(df['close'], 14)\n    ma20 = df['close'].rolling(20).mean()\n    signals = (rsi < 38) & (df['close'] > ma20)\n    return signals.astype(int)\n`,
    },
  };
}

export const RUNS_MAP = new Map<string, RunDetail>([
  [
    "run_20260815_btc_momentum",
    generateRunData("run_20260815_btc_momentum", "Backtest BTC-USDT 20/50 MA + RSI Momentum with 1h breakout", "BTC-USDT", 90),
  ],
  [
    "run_20260814_eth_funding_arb",
    generateRunData("run_20260814_eth_funding_arb", "ETH Funding Rate Z-Score Arbitrage with Volatility Filter", "ETH-USDT", 60),
  ],
  [
    "run_20260812_sol_breakout",
    generateRunData("run_20260812_sol_breakout", "SOL-USDT Intraday Volume Breakout & VWAP Reversion", "SOL-USDT", 45),
  ],
  [
    "run_20260810_alpha101_comp",
    generateRunData("run_20260810_alpha101_comp", "Kakushadze Alpha #001 vs #101 Cross-Sectional Alpha Portfolio", "BTC-USDT", 120),
  ],
]);
