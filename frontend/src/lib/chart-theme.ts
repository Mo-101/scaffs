export function getChartTheme(isDark = true) {
  return {
    backgroundColor: "transparent",
    textColor: isDark ? "#94a3b8" : "#64748b",
    lineColor: isDark ? "#334155" : "#e2e8f0",
    splitLineColor: isDark ? "#1e293b" : "#f1f5f9",
    upColor: "#10b981",
    downColor: "#ef4444",
  };
}