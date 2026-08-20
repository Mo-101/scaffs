export function isReportWorthyRun(run: any): boolean {
  return Boolean(run && (run.status === "completed" || run.status === "success" || run.metrics));
}