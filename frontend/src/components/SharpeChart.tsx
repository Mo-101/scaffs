import React, { useState, useMemo } from "react";
import { TrendingUp, Shield, BarChart3, Activity, CheckCircle2 } from "lucide-react";
import { cn } from "../lib/utils";

interface SharpeChartProps {
  points: Array<{ time: string; equity: number; drawdown: number; sharpe?: number; sortino?: number }>;
  currentSharpe: number | null;
  currentSortino: number | null;
  timeframe?: string;
  strategyId?: string;
  winRate?: number | null;
  profitFactor?: number | null;
  /** Calibrated tier label/color computed by the caller (see PaperTrading.tsx's
   * sharpeRating/sharpeColor) -- this component must never invent its own. */
  sharpeRating?: string;
  sharpeColor?: string;
}

export const SharpeChart: React.FC<SharpeChartProps> = ({
  points,
  currentSharpe,
  currentSortino,
  timeframe,
  strategyId,
  winRate,
  profitFactor,
  sharpeRating,
  sharpeColor,
}) => {
  const [chartMode, setChartMode] = useState<"sharpe" | "equity" | "drawdown">("sharpe");

  // Real data only -- never fabricate points. A session with no rolling
  // sharpe/sortino samples yet renders an empty chart, not a plausible-looking
  // synthetic curve.
  const validPoints = useMemo(() => {
    if (!points || points.length === 0) return [];
    return points.map((p, i) => ({
      time: p.time || `${i}`,
      equity: p.equity,
      drawdown: Math.abs(p.drawdown || 0),
      sharpe: p.sharpe,
      sortino: p.sortino,
    }));
  }, [points]);

  // Calculate SVG paths
  const chartHeight = 180;
  const chartWidth = 600;
  const padding = { top: 20, right: 30, bottom: 25, left: 45 };

  const values = useMemo(() => {
    const raw =
      chartMode === "sharpe"
        ? validPoints.map((p) => p.sharpe)
        : chartMode === "equity"
          ? validPoints.map((p) => p.equity)
          : validPoints.map((p) => p.drawdown);
    return raw.filter((v): v is number => v != null && Number.isFinite(v));
  }, [validPoints, chartMode]);

  const hasChartData = values.length >= 2;
  const minVal = hasChartData ? Math.min(...values) : 0;
  const maxVal = hasChartData ? Math.max(...values) : 1;
  const range = maxVal - minVal || 1;

  const svgPath = useMemo(() => {
    if (values.length < 2) return "";
    const innerW = chartWidth - padding.left - padding.right;
    const innerH = chartHeight - padding.top - padding.bottom;

    return values
      .map((val, idx) => {
        const x = padding.left + (idx / (values.length - 1)) * innerW;
        const y = padding.top + innerH - ((val - minVal) / range) * innerH;
        return `${idx === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values, minVal, range, chartWidth, chartHeight, padding]);

  const areaPath = useMemo(() => {
    if (!svgPath) return "";
    const innerW = chartWidth - padding.left - padding.right;
    const innerH = chartHeight - padding.top - padding.bottom;
    const lastX = padding.left + innerW;
    const bottomY = padding.top + innerH;
    return `${svgPath} L ${lastX} ${bottomY} L ${padding.left} ${bottomY} Z`;
  }, [svgPath, chartWidth, chartHeight, padding]);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-950/80 p-5 shadow-xl backdrop-blur-sm">
      {/* Header & Mode Selector */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800/80 pb-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
            <TrendingUp className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-white text-base">Sharpe Ratio & Edge Performance</h3>
              <span
                className={cn(
                  "rounded bg-gray-900/60 border border-gray-800 px-2 py-0.5 text-xs font-semibold",
                  sharpeColor || "text-gray-300",
                )}
              >
                {currentSharpe != null ? `Sharpe ${currentSharpe.toFixed(2)}` : "Sharpe N/A"}
                {sharpeRating ? ` (${sharpeRating})` : ""}
              </span>
            </div>
            <p className="text-xs text-gray-400">
              Annualized risk-adjusted return metric across {validPoints.length} rolling execution batches{strategyId ? ` · ${strategyId}` : ""}{timeframe ? ` (${timeframe})` : ""}
            </p>
          </div>
        </div>

        {/* Toggle buttons */}
        <div className="flex items-center rounded-lg border border-gray-800 bg-gray-900 p-1">
          <button
            onClick={() => setChartMode("sharpe")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all",
              chartMode === "sharpe"
                ? "bg-emerald-500/20 text-emerald-300 shadow-sm border border-emerald-500/40"
                : "text-gray-400 hover:text-gray-200",
            )}
          >
            <Activity className="h-3.5 w-3.5" />
            Rolling Sharpe
          </button>
          <button
            onClick={() => setChartMode("equity")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all",
              chartMode === "equity"
                ? "bg-blue-500/20 text-blue-300 shadow-sm border border-blue-500/40"
                : "text-gray-400 hover:text-gray-200",
            )}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Equity ($)
          </button>
          <button
            onClick={() => setChartMode("drawdown")}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all",
              chartMode === "drawdown"
                ? "bg-amber-500/20 text-amber-300 shadow-sm border border-amber-500/40"
                : "text-gray-400 hover:text-gray-200",
            )}
          >
            <Shield className="h-3.5 w-3.5" />
            Drawdown (%)
          </button>
        </div>
      </div>

      {/* Main Chart Graphic */}
      <div className="relative w-full">
        {!hasChartData && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-gray-500">
            Not enough samples yet for this view
          </div>
        )}
        <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-44 overflow-visible">
          <defs>
            <linearGradient id="sharpeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="drawdownGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          {hasChartData &&
            [0, 0.33, 0.66, 1].map((pct, i) => {
              const innerH = chartHeight - padding.top - padding.bottom;
              const y = padding.top + innerH * pct;
              const labelVal = maxVal - pct * range;
              return (
                <g key={i}>
                  <line
                    x1={padding.left}
                    y1={y}
                    x2={chartWidth - padding.right}
                    y2={y}
                    stroke="#374151"
                    strokeDasharray="3 3"
                    strokeWidth="0.8"
                    opacity="0.4"
                  />
                  <text x={padding.left - 8} y={y + 3} textAnchor="end" fill="#9ca3af" fontSize="9" fontFamily="monospace">
                    {chartMode === "equity"
                      ? `$${Math.round(labelVal).toLocaleString()}`
                      : chartMode === "drawdown"
                        ? `-${labelVal.toFixed(1)}%`
                        : labelVal.toFixed(2)}
                  </text>
                </g>
              );
            })}

          {/* Area Fill */}
          <path
            d={areaPath}
            fill={
              chartMode === "sharpe"
                ? "url(#sharpeGradient)"
                : chartMode === "equity"
                  ? "url(#equityGradient)"
                  : "url(#drawdownGradient)"
            }
          />

          {/* Stroke Path */}
          <path
            d={svgPath}
            fill="none"
            stroke={
              chartMode === "sharpe"
                ? "#10b981"
                : chartMode === "equity"
                  ? "#3b82f6"
                  : "#f59e0b"
            }
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* X Axis Time Labels */}
          {validPoints.length > 0 && (
            <g>
              <text x={padding.left} y={chartHeight - 5} fill="#6b7280" fontSize="9">
                {validPoints[0]?.time}
              </text>
              <text x={chartWidth / 2} y={chartHeight - 5} textAnchor="middle" fill="#6b7280" fontSize="9">
                {validPoints[Math.floor(validPoints.length / 2)]?.time}
              </text>
              <text x={chartWidth - padding.right} y={chartHeight - 5} textAnchor="end" fill="#6b7280" fontSize="9">
                {validPoints[validPoints.length - 1]?.time}
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* Metrics Row Breakdown -- only real, prop-driven values. No BTC
          benchmark or bootstrap-confidence tiles: neither had a real data
          source wired into this component, so they were always fabricated. */}
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-gray-800/80 pt-4">
        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>Sortino Ratio</span>
            <Activity className="h-3.5 w-3.5 text-sky-400" />
          </div>
          <div className="mt-1 text-lg font-bold text-sky-400">
            {currentSortino != null ? currentSortino.toFixed(2) : "N/A"}
          </div>
          <p className="text-[10px] text-gray-500">Downside-deviation adjusted</p>
        </div>

        <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-3">
          <div className="flex items-center justify-between text-xs text-gray-400">
            <span>Win Rate Edge</span>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <div className="mt-1 text-lg font-bold text-emerald-400">
            {winRate != null ? `${(winRate * 100).toFixed(1)}%` : "N/A"}
          </div>
          <p className="text-[10px] text-gray-500">
            Profit Factor: {profitFactor != null ? profitFactor.toFixed(2) : "N/A"}
          </p>
        </div>
      </div>
    </div>
  );
};
