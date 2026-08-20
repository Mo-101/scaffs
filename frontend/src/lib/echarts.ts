import * as echarts from "echarts";

export { echarts };
export const CHART_GROUP = "vibe_charts";
export function connectCharts(group = CHART_GROUP) {
  try {
    echarts.connect(group);
  } catch {
    // ignore
  }
}