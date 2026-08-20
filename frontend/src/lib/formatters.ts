export const DISPLAY_ORDER: string[] = [
  "total_return",
  "annualized_return",
  "sharpe_ratio",
  "sortino_ratio",
  "max_drawdown",
  "win_rate",
  "profit_factor",
  "total_trades",
];

export function abbreviateNum(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "--";
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(2);
}

export function formatMetricVal(key: string, val: any): string {
  if (val == null) return "--";
  if (typeof val === "number") {
    if (key.includes("rate") || key.includes("pct") || key.includes("return") || key.includes("drawdown")) {
      return `${(val * (Math.abs(val) <= 1 ? 100 : 1)).toFixed(2)}%`;
    }
    return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(val);
}

export function formatTimestamp(ts: string | number | Date | null | undefined): string {
  if (!ts) return "--";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

export function getMetricLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function metricSentiment(key: string, val: any): "positive" | "negative" | "neutral" {
  const num = Number(val);
  if (isNaN(num)) return "neutral";
  if (key.includes("drawdown") || key.includes("loss")) {
    return num > 0 ? "negative" : "positive";
  }
  return num > 0 ? "positive" : num < 0 ? "negative" : "neutral";
}