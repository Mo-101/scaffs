export function applySwarmEvent(status: any, event: any) {
  return { ...status, ...event };
}

export function buildSwarmStatusFromStarted(data: any) {
  return { status: "started", ...data };
}

export function buildSwarmStatusFromToolResultPreview(data: any) {
  return { status: "tool_result", ...data };
}