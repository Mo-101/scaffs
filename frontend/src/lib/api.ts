// Auto-generated minimal API client stub

export type AlphaBenchResult = any;
export type AlphaBenchTopRow = any;
export type AlphaCompareResult = any;
export type AlphaDetailResponse = any;
export type AlphaSummary = any;
export type AutopilotEvidenceRunItem = any;
export type BacktestMetrics = any;
export type ChannelRuntimeStatus = any;
export type DataSourceSettings = any;
export type DbStatusResponse = any;
export type EquityPoint = any;
export type GoalSnapshot = any;
export type GridEngineState = any;
export type LLMProviderOption = any;
export type LLMSettings = any;
export type LiveAction = any;
export type LiveAuthorizeResponse = any;
export type LiveBrokerStatus = any;
export type LiveHalted = any;
export type LiveMandateLimits = any;
export type LiveStatus = any;
export type MandateCommitted = any;
export type MandateProfile = any;
export type MandateProposal = any;
export type MorningGloryFundingState = any;
export type PaperDecisionHealth = any;
export type PaperDecisionHealthWorker = any;
export type PaperProviderHealth = any;
export type PaperSessionSummary = any;
export type PositionMetadata = any;
export type RunCard = any;
export type RunData = any;
export type RunListItem = any;
export type SessionItem = any;

export class ApiError extends Error {}
export const AUTH_REQUIRED_MESSAGE = "Authentication required";
export const isAuthRequiredError = (e: any): boolean => e instanceof ApiError || (e?.message ?? "").includes(AUTH_REQUIRED_MESSAGE);
export const isFuturesClosedTrade = (t: any): boolean => !!(t && t.exit_price);

async function get(path: string): Promise<any> {
  const res = await fetch(path);
  if (!res.ok) throw new ApiError(`${res.status}: ${res.statusText}`);
  return res.json();
}

async function post(path: string, body?: any): Promise<any> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(`${res.status}: ${res.statusText}`);
  return res.json();
}

export const api = {
  acceleratePaperTrades: async (payload?: any): Promise<any> => post("/paper-sessions/accelerate", payload),
  alphaBenchStreamUrl: "",
  alphaCompareStreamUrl: "",
  authorizeLive: async (..._args: any[]): Promise<any> => {},
  cancelSession: async (..._args: any[]): Promise<any> => {},
  commitMandate: async (..._args: any[]): Promise<any> => {},
  createAlphaBench: async (..._args: any[]): Promise<any> => {},
  createAlphaCompare: async (..._args: any[]): Promise<any> => {},
  createGoal: async (..._args: any[]): Promise<any> => {},
  createSession: async (..._args: any[]): Promise<any> => {},
  deleteSession: async (..._args: any[]): Promise<any> => {},
  getChannelStatus: async (..._args: any[]): Promise<any> => {},
  getDataSourceSettings: async (..._args: any[]): Promise<any> => {},
  getDbStatus: async (..._args: any[]): Promise<any> => {},
  getGoal: async (..._args: any[]): Promise<any> => {},
  getLLMSettings: async (..._args: any[]): Promise<any> => {},
  getLiveStatus: async (..._args: any[]): Promise<any> => {},
  getPaperDecisionHealth: async (): Promise<any> => get("/paper-sessions/decision-health"),
  getPaperProviderHealth: async (): Promise<any> => get("/paper-sessions/provider-health"),
  getPaperSessionLivePrices: async (id: string): Promise<any> => get(`/paper-sessions/${encodeURIComponent(id)}/live-prices`),
  getPaperTradingNotifications: async (after?: string): Promise<any> =>
    get(`/paper-trading/notifications${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  getRun: async (..._args: any[]): Promise<any> => {},
  getRunCode: async (..._args: any[]): Promise<any> => {},
  getRunPine: async (..._args: any[]): Promise<any> => {},
  getSessionMessages: async (..._args: any[]): Promise<any> => {},
  haltLive: async (..._args: any[]): Promise<any> => {},
  listAutopilotEvidenceRuns: async (..._args: any[]): Promise<any> => {},
  listPaperSessions: async (): Promise<any> => {
    const index = await get("/api/paper/sessions");
    return index.sessions ?? [];
  },
  listRuns: async (..._args: any[]): Promise<any> => {},
  listSessions: async (): Promise<any> => get("/sessions"),
  rebalanceGrid: async (..._args: any[]): Promise<any> => {},
  renameSession: async (..._args: any[]): Promise<any> => {},
  runGovernedBacktest: async (..._args: any[]): Promise<any> => {},
  saveGridState: async (..._args: any[]): Promise<any> => {},
  sendMessage: async (..._args: any[]): Promise<any> => {},
  sseUrl: "",
  startChannels: async (..._args: any[]): Promise<any> => {},
  startLiveRunner: async (..._args: any[]): Promise<any> => {},
  stopChannels: async (..._args: any[]): Promise<any> => {},
  stopLiveRunner: async (..._args: any[]): Promise<any> => {},
  switchTestnet: async (payload?: any): Promise<any> => post("/paper-sessions/switch-testnet", payload),
  syncDb: async (..._args: any[]): Promise<any> => {},
  triggerMorningGlory: async (..._args: any[]): Promise<any> => {},
  updateDataSourceSettings: async (..._args: any[]): Promise<any> => {},
  updateGoal: async (..._args: any[]): Promise<any> => {},
  updateGoalStatus: async (..._args: any[]): Promise<any> => {},
  updateLLMSettings: async (..._args: any[]): Promise<any> => {},
  uploadFile: async (..._args: any[]): Promise<any> => {},
};