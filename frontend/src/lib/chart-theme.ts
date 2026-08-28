export function getChartTheme(isDark = true) {
  return {
    backgroundColor: "transparent",
    textColor: isDark ? "#94a3b8" : "#64748b",
    lineColor: isDark ? "#334155" : "#e2e8f0",
    splitLineColor: isDark ? "#1e293b" : "#f1f5f9",
    upColor: "#10b981",
    downColor: "#ef4444",
    bollColor: isDark ? "#a855f7" : "#9333ea",
    volumeUp: "rgba(16, 185, 129, 0.5)",
    volumeDown: "rgba(239, 68, 68, 0.5)",
    gridColor: isDark ? "#1e293b" : "#e2e8f0",
    infoColor: isDark ? "#38bdf8" : "#0284c7",
    warningColor: isDark ? "#f59e0b" : "#d97706",
    tooltipBg: isDark ? "#0f172a" : "#ffffff",
    tooltipBorder: isDark ? "#334155" : "#e2e8f0",
    tooltipText: isDark ? "#e2e8f0" : "#1e293b",
    axisColor: isDark ? "#475569" : "#94a3b8",
  };
}