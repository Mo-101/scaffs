// Auto-generated minimal API client stub

import { getApiAuthKey } from "@/lib/apiAuth";

// Native EventSource can't send an Authorization header, so these stream
// endpoints accept the API key as a query param instead (see
// require_event_stream_auth in api_server.py).
function eventStreamUrl(path: string, params?: Record<string, string>): string {
  const qs = new URLSearchParams(params);
  const key = getApiAuthKey();
  if (key) qs.set("api_key", key);
  const query = qs.toString();
  return `${path}${query ? `?${query}` : ""}`;
}

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
export type IndicatorPoint = any;
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
export type PriceBar = any;
export type RunCard = any;
export type RunData = any;
export type RunListItem = any;
export type SessionItem = any;
export type TradeMarker = any;
export type ValidationData = any;

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}
export const AUTH_REQUIRED_MESSAGE = "Authentication required";
export const isAuthRequiredError = (e: any): boolean => e instanceof ApiError || (e?.message ?? "").includes(AUTH_REQUIRED_MESSAGE);
export const isFuturesClosedTrade = (t: any): boolean => !!(t && t.exit_price);

async function errorMessageFrom(res: Response): Promise<string> {
  try {
    const data = await res.clone().json();
    const msg = data?.message || data?.error || data?.detail;
    if (typeof msg === "string" && msg) return msg;
  } catch {
    // response body wasn't JSON (or was empty) -- fall through to the status line
  }
  return `${res.status}: ${res.statusText}`;
}

async function get(path: string): Promise<any> {
  const res = await fetch(path);
  if (!res.ok) throw new ApiError(await errorMessageFrom(res), res.status);
  return res.json();
}

async function post(path: string, body?: any): Promise<any> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(await errorMessageFrom(res), res.status);
  return res.json();
}

export const api = {
  // Demo-only: fast-forwards synthetic trades in the in-memory fixture. Has
  // no real-engine equivalent, so this stays pointed at /demo/* explicitly
  // rather than hitting the real engine's /paper-sessions/* (which would 404).
  acceleratePaperTrades: async (sessionId?: string, count?: number): Promise<any> =>
    post("/demo/paper-sessions/accelerate", { sessionId: sessionId || "all", count: count ?? 10 }),
  alphaBenchStreamUrl: (jobId: string): string => eventStreamUrl(`/alpha/bench/${encodeURIComponent(jobId)}/stream`),
  alphaCompareStreamUrl: (jobId: string): string => eventStreamUrl(`/alpha/compare/${encodeURIComponent(jobId)}/stream`),
  authorizeLive: async (..._args: any[]): Promise<any> => {},
  cancelSession: async (..._args: any[]): Promise<any> => {},
  commitMandate: async (..._args: any[]): Promise<any> => {},
  createAlphaBench: async (..._args: any[]): Promise<any> => {},
  createAlphaCompare: async (..._args: any[]): Promise<any> => {},
  createGoal: async (..._args: any[]): Promise<any> => {},
  createSession: async (..._args: any[]): Promise<any> => {},
  deleteSession: async (sessionId: string): Promise<any> => {
    const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    if (!res.ok) throw new ApiError(await errorMessageFrom(res), res.status);
    return res.json();
  },
  getAlpha: async (alphaId: string): Promise<any> => get(`/alpha/${encodeURIComponent(alphaId)}`),
  getBinanceTestnetStatus: async (): Promise<any> => get("/paper-sessions/binance-testnet/status"),
  getBinanceTestnetBalance: async (): Promise<any> => get("/paper-sessions/binance-testnet/balance"),
  getBinanceTestnetPositions: async (symbol?: string): Promise<any> =>
    get(`/paper-sessions/binance-testnet/positions${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  placeBinanceTestnetOrder: async (order: any): Promise<any> => post("/paper-sessions/binance-testnet/order", order),
  syncBinanceMarketData: async (): Promise<any> => post("/paper-sessions/binance-testnet/market-data/sync"),
  getBinanceMarketData: async (symbol?: string): Promise<any> =>
    get("/paper-sessions/binance-testnet/market-data" + (symbol ? `?symbol=${encodeURIComponent(symbol)}` : "")),
  syncMarketData: async (provider: string): Promise<any> => post(`/paper-sessions/market-data/sync/${provider}`),
  syncAllMarketData: async (): Promise<any> => post("/paper-sessions/market-data/sync-all"),
  getMarketData: async (provider: string, kind: string = "tickers", symbol?: string): Promise<any> =>
    get(`/paper-sessions/market-data/${provider}?kind=${kind}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`),
  getMarketDataStatus: async (provider?: string): Promise<any> =>
    get("/paper-sessions/market-data-status" + (provider ? `?provider=${encodeURIComponent(provider)}` : "")),
  getSignalQueuePending: async (limit?: number): Promise<any> =>
    get(`/paper-sessions/signal-queue/pending${limit ? `?limit=${limit}` : ""}`),
  getSignalQueueHistory: async (limit?: number): Promise<any> =>
    get(`/paper-sessions/signal-queue/history${limit ? `?limit=${limit}` : ""}`),
  dispatchQueuedSignal: async (payload: any): Promise<any> => post("/paper-sessions/signal-queue/dispatch", payload),
  syncIdimSignals: async (payload?: any): Promise<any> => post("/paper-sessions/signal-queue/sync-idim", payload),
  runPositionReconciler: async (dryRun?: boolean): Promise<any> =>
    post(`/paper-sessions/position-reconciler/run?dry_run=${dryRun ?? true}`),
  getChannelStatus: async (): Promise<any> => get("/channels/status"),
  getDataSourceSettings: async (): Promise<any> => get("/settings/data-sources"),
  getDbStatus: async (): Promise<any> => get("/paper-sessions/db-status").then((r) => r.db),
  getGoal: async (..._args: any[]): Promise<any> => {},
  getLLMSettings: async (): Promise<any> => get("/settings/llm"),
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
  listAlphas: async (params: { zoo?: string; theme?: string; universe?: string; limit?: number } = {}): Promise<any> => {
    const qs = new URLSearchParams();
    if (params.zoo) qs.set("zoo", params.zoo);
    if (params.theme) qs.set("theme", params.theme);
    if (params.universe) qs.set("universe", params.universe);
    if (params.limit) qs.set("limit", String(params.limit));
    const query = qs.toString();
    return get(`/alpha/list${query ? `?${query}` : ""}`);
  },
  listAutopilotEvidenceRuns: async (..._args: any[]): Promise<any> => {},
  listPaperSessions: async (scope: string = "active"): Promise<any> =>
    get(`/paper-sessions?scope=${encodeURIComponent(scope)}`),
  listRuns: async (..._args: any[]): Promise<any> => {},
  listSessions: async (): Promise<any> => get("/sessions"),
  rebalanceGrid: async (..._args: any[]): Promise<any> => {},
  renameSession: async (..._args: any[]): Promise<any> => {},
  runGovernedBacktest: async (..._args: any[]): Promise<any> => {},
  saveGridState: async (..._args: any[]): Promise<any> => {},
  sendMessage: async (..._args: any[]): Promise<any> => {},
  sseUrl: (sessionId: string, params?: Record<string, string>): string =>
    eventStreamUrl(`/sessions/${encodeURIComponent(sessionId)}/events`, params),
  startChannels: async (): Promise<any> => post("/channels/start"),
  startLiveRunner: async (..._args: any[]): Promise<any> => {},
  stopChannels: async (): Promise<any> => post("/channels/stop"),
  stopLiveRunner: async (..._args: any[]): Promise<any> => {},
  // Demo-only: synthetic "100 verified trades" gate against the in-memory
  // fixture's trade counts. No real-engine equivalent -- see acceleratePaperTrades.
  switchTestnet: async (payload?: any): Promise<any> => post("/demo/paper-sessions/switch-testnet", payload),
  syncDb: async (): Promise<any> => post("/paper-sessions/db-sync"),
  triggerMorningGlory: async (..._args: any[]): Promise<any> => {},
  updateDataSourceSettings: async (payload: any): Promise<any> => {
    const res = await fetch("/settings/data-sources", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new ApiError(`${res.status}: ${res.statusText}`);
    return res.json();
  },
  updateGoal: async (..._args: any[]): Promise<any> => {},
  updateGoalStatus: async (..._args: any[]): Promise<any> => {},
  updateLLMSettings: async (payload: any): Promise<any> => {
    const res = await fetch("/settings/llm", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new ApiError(`${res.status}: ${res.statusText}`);
    return res.json();
  },
  uploadFile: async (..._args: any[]): Promise<any> => {},
};