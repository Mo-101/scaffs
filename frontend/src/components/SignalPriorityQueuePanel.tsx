import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import { toast } from "sonner";
import {
  Flame,
  RefreshCw,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Layers,
  Activity,
  SendHorizontal,
  Play,
  Pause,
  Settings,
} from "lucide-react";

interface QueuedSignal {
  id: string;
  source_signal_id?: string;
  producer: string;
  symbol: string;
  side: string;
  timeframe: string;
  raw_score: number;
  topsis_score?: number;
  target_strategy: string;
  status: string;
  created_at: string;
  criteria_vector?: Record<string, any>;
  execution_order_id?: string;
  execution_client_order_id?: string;
  rejection_reason?: string;
}

const AUTO_NOTIONAL_KEY = "idim_auto_notional_usd";
const AUTO_EXECUTE_KEY = "idim_auto_execute_enabled";
const AUTO_THRESHOLD_KEY = "idim_auto_execute_threshold";
const POLL_INTERVAL_MS = 5_000;

const producerLabel = (producer?: string) => {
  switch ((producer || "").toLowerCase()) {
    case "sigmalui":
    case "sigmalui_soul":
      return "SigmaLUI Premium";
    case "idim_ikang":
      return "IDIM Ikang";
    case "scaffs_native":
      return "Scaffs Native";
    case "scaffs_picker":
      return "Scaffs Picker";
    default:
      return producer || "Unknown source";
  }
};

export const SignalPriorityQueuePanel: React.FC = () => {
  const [pendingSignals, setPendingSignals] = useState<QueuedSignal[]>([]);
  // Recent premium activity. Rendered as trailing rows of the single signal table
  // below -- it deliberately has no section container of its own.
  const [recentSignals, setRecentSignals] = useState<QueuedSignal[]>([]);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [dispatchingId, setDispatchingId] = useState<string | null>(null);

  // Auto-execute is SERVER state, not browser state. It used to live in
  // localStorage, which meant the dashboard dispatched orders on its own and no
  // server-side flag could stop it -- a "paused" backend plus an open tab was
  // still a live trading system. The server is now the single authority; this is
  // just a mirror of it.
  const [autoExecute, setAutoExecute] = useState<boolean>(false);
  const [autoLoaded, setAutoLoaded] = useState<boolean>(false);
  const [autoBusy, setAutoBusy] = useState<boolean>(false);
  const [notionalUsd, setNotionalUsd] = useState<number>(() => {
    try {
      const saved = Number(localStorage.getItem(AUTO_NOTIONAL_KEY));
      return saved > 0 ? saved : 100;
    } catch {
      return 100;
    }
  });
  const [threshold, setThreshold] = useState<number>(() => {
    try {
      const saved = Number(localStorage.getItem(AUTO_THRESHOLD_KEY));
      return saved >= 0 ? saved : 80;
    } catch {
      return 80;
    }
  });
  const [showSettings, setShowSettings] = useState<boolean>(false);

  const autoDispatchingRef = useRef<Set<string>>(new Set());
  const previousIdsRef = useRef<Set<string>>(new Set());

  const fetchQueue = useCallback(async () => {
    try {
      const [pending, history] = await Promise.all([
        api.getSignalQueuePending(30),
        api.getSignalQueueHistory(30),
      ]);
      if (pending?.ok) setPendingSignals(pending.signals || []);
      if (history?.ok) {
        setRecentSignals(
          (history.history || []).filter((signal: QueuedSignal) =>
            signal.producer?.toLowerCase().startsWith("sigmalui")
          ).slice(0, 8)
        );
      }
    } catch (err) {
      console.error("Failed to load pending queue:", err);
    }
  }, []);

  useEffect(() => {
    void fetchQueue();
    const interval = setInterval(() => void fetchQueue(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  // Mirror the server's auto-execute flag. Polled so a change made elsewhere
  // (another operator, another tab, the API) shows up here rather than this tab
  // believing a stale value.
  useEffect(() => {
    const read = async () => {
      try {
        const res = await api.getAutoExecute();
        if (res?.ok) {
          setAutoExecute(Boolean(res.enabled));
          setAutoLoaded(true);
        }
      } catch {
        /* leave the last known value; the toggle reports its own failures */
      }
    };
    void read();
    const id = setInterval(() => void read(), POLL_INTERVAL_MS * 2);
    return () => clearInterval(id);
  }, []);

  // NOTE: the browser no longer auto-dispatches. The worker and the Idim daemon
  // read the same server-side flag every poll cycle and execute there, so
  // auto-execute behaves identically whether or not this page is open.

  const handleSyncAll = async () => {
    setSyncing(true);
    try {
      const [sigma, idim] = await Promise.all([
        api.syncSigmaluiSignals({ notional_usd: notionalUsd }),
        api.syncIdimSignals({ notional_usd: notionalUsd }),
      ]);
      toast.success("Signal sources refreshed", {
        description: `SigmaLUI: ${sigma?.signals_examined ?? 0} examined, ${sigma?.enqueued_count ?? 0} new. IDIM: ${idim?.enqueued_count ?? 0} new.`,
      });
      await fetchQueue();
    } catch (err: any) {
      toast.error("Signal refresh failed", { description: err?.message || String(err) });
    } finally {
      setSyncing(false);
    }
  };

  const handleDispatch = async (signal: QueuedSignal) => {
    setDispatchingId(signal.id);
    try {
      const res = await api.dispatchQueuedSignal({ queue_id: signal.id, notional_usd: notionalUsd });
      if (res?.ok) {
        toast.success(`Dispatched ${producerLabel(signal.producer)} signal`, {
          description: `${signal.symbol} ${signal.side} · Binance Testnet Order ID: ${res.order_id} (${res.client_order_id})`,
        });
        await fetchQueue();
      } else {
        toast.error(`Execution blocked: ${producerLabel(signal.producer)}`, {
          description: `${signal.symbol} ${signal.side} · ${res?.reason || res?.error}`,
        });
      }
    } catch (err: any) {
      toast.error(`Dispatch failed: ${producerLabel(signal.producer)}`, {
        description: `${signal.symbol} ${signal.side} · ${err?.message || String(err)}`,
      });
    } finally {
      setDispatchingId(null);
    }
  };

  const toggleAutoExecute = async () => {
    const next = !autoExecute;
    setAutoBusy(true);
    try {
      const res = await api.setAutoExecute(next);
      if (res?.ok) {
        setAutoExecute(Boolean(res.enabled));
        toast.success(res.enabled ? "Auto-execute ON" : "Auto-execute OFF", {
          description: res.enabled
            ? "The worker and Idim daemon will dispatch on their next cycle."
            : "Signals will queue for manual dispatch. No restart needed.",
        });
      } else {
        toast.error("Could not change auto-execute", { description: res?.detail || "server rejected the change" });
      }
    } catch (err: any) {
      // Do not flip the UI on failure -- showing OFF while the server is still
      // ON is exactly the confusion this change exists to remove.
      toast.error("Could not change auto-execute", { description: err?.message || String(err) });
    } finally {
      setAutoBusy(false);
    }
  };

  const canonicalId = (s: QueuedSignal) =>
    (s.criteria_vector?.canonical_id as string | undefined) ?? s.target_strategy;

  const rebalanceCount = pendingSignals.filter((s) => canonicalId(s) === "periodic_equal_weight_rebalance").length;
  const gridCount = pendingSignals.filter((s) => canonicalId(s).startsWith("bounded_grid_v1")).length;
  const gloryCount = pendingSignals.filter((s) => canonicalId(s) === "funding_rate_zscore").length;

  return (
    <div className="rounded-xl border border-amber-500/20 bg-slate-950/80 p-4 shadow-xl backdrop-blur-md">
      {/* Header — single row, compact */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-amber-600 to-red-500 shadow-md shadow-amber-500/30">
          <Flame className="h-4 w-4 text-white animate-pulse" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold text-white leading-none">
              Multi-Source Signal Queue &amp; Strategy Router
            </h2>
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20 leading-none">
              PREMIUM FEED ACTIVE
            </span>
          </div>
          <p className="text-[10px] text-slate-400 mt-0.5 hidden sm:block">
            SigmaLUI Premium, IDIM Ikang and Scaffs native signals · collision-guarded execution · Binance USDⓈ-M
          </p>
        </div>
        {/* Strategy pills */}
        <div className="flex items-center gap-2 text-[10px]">
          <span className="flex items-center gap-1 rounded border border-cyan-500/20 bg-cyan-500/10 px-2 py-0.5 font-bold text-cyan-300">
            <Layers className="h-3 w-3" />Rebalance {rebalanceCount}
          </span>
          <span className="flex items-center gap-1 rounded border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 font-bold text-indigo-300">
            <Activity className="h-3 w-3" />Grid {gridCount}
          </span>
          <span className="flex items-center gap-1 rounded border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 font-bold text-amber-300">
            <Zap className="h-3 w-3" />Glory {gloryCount}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleAutoExecute}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-all",
              autoExecute
                ? "bg-emerald-600/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-600/30"
                : "bg-slate-800/50 text-slate-300 border-slate-700 hover:bg-slate-800"
            )}
            title={autoExecute ? "Auto-execute is enabled" : "Auto-execute is disabled"}
          >
            {autoExecute ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
            {autoExecute ? "Auto ON" : "Auto OFF"}
          </button>

          <button
            onClick={() => setShowSettings((s) => !s)}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800/50 text-slate-300 border border-slate-700 hover:bg-slate-800 transition-all"
            title="Auto-execute settings"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={handleSyncAll}
            disabled={syncing}
            className="flex items-center gap-1.5 rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs font-medium text-amber-300 border border-amber-500/30 hover:bg-amber-600/30 transition-all disabled:opacity-50 flex-shrink-0"
          >
            <RefreshCw className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Refreshing..." : "Refresh All Sources"}
          </button>
        </div>
      </div>

      {showSettings && (
        <div className="mb-3 grid grid-cols-1 sm:grid-cols-2 gap-3 rounded-lg border border-slate-700/50 bg-slate-900/50 p-3 text-xs text-slate-300">
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Notional per auto-execution (USDT)</span>
            <input
              type="number"
              min={5}
              step={5}
              value={notionalUsd}
              onChange={(e) => {
                const val = Number(e.target.value);
                setNotionalUsd(val);
                try {
                  localStorage.setItem(AUTO_NOTIONAL_KEY, String(val));
                } catch {}
              }}
              className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 focus:border-amber-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-400">Auto-execute raw score threshold</span>
            <input
              type="number"
              min={0}
              max={100}
              step={1}
              value={threshold}
              onChange={(e) => {
                const val = Number(e.target.value);
                setThreshold(val);
                try {
                  localStorage.setItem(AUTO_THRESHOLD_KEY, String(val));
                } catch {}
              }}
              className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 focus:border-amber-500 focus:outline-none"
            />
          </label>
        </div>
      )}

      {/* Active Priority Queue — scrollable, max 5 rows visible */}
      {pendingSignals.length === 0 && recentSignals.length === 0 ? (
        <div className="py-5 text-center text-xs text-slate-500">
          No signals are waiting for manual dispatch and no recent activity has been recorded.
        </div>
      ) : (
        <div className="overflow-auto" style={{ maxHeight: "220px" }}>
          <table className="w-full text-left text-xs text-slate-300 min-w-[640px]">
            <thead className="sticky top-0 bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider z-10">
              <tr>
                <th className="p-2">Rank / TOPSIS</th>
                <th className="p-2">Source / Symbol</th>
                <th className="p-2">Side</th>
                <th className="p-2">Strategy</th>
                <th className="p-2">Score</th>
                <th className="p-2 text-right">Execute / Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {pendingSignals.map((sig, idx) => {
                const isLong =
                  sig.side.toUpperCase() === "LONG" || sig.side.toUpperCase() === "BUY";
                const topsis =
                  sig.topsis_score !== undefined
                    ? Number(sig.topsis_score).toFixed(3)
                    : "—";
                return (
                  <tr key={sig.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="p-2 font-mono">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className={`inline-block h-4 w-4 text-center leading-4 rounded-full text-[9px] font-bold ${
                            idx === 0
                              ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {idx + 1}
                        </span>
                        <span className="text-amber-400 font-bold">{topsis}</span>
                      </span>
                    </td>
                    <td className="p-2">
                      <span className="block font-bold text-white">{sig.symbol}</span>
                      <span className={`mt-0.5 inline-flex rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                        sig.producer?.toLowerCase().startsWith("sigmalui")
                          ? "border border-violet-500/30 bg-violet-500/10 text-violet-300"
                          : "border border-slate-700 bg-slate-800/70 text-slate-400"
                      }`}>
                        {producerLabel(sig.producer)}
                      </span>
                    </td>
                    <td className="p-2">
                      <span
                        className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded font-bold text-[10px] ${
                          isLong
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {isLong ? (
                          <ArrowUpRight className="h-3 w-3" />
                        ) : (
                          <ArrowDownRight className="h-3 w-3" />
                        )}
                        {sig.side}
                      </span>
                    </td>
                    <td className="p-2 font-mono text-cyan-300 text-[10px]">
                      {canonicalId(sig)}
                      <span className="block text-[8px] text-slate-500">{sig.target_strategy}</span>
                    </td>
                    <td className="p-2 font-mono text-emerald-400 font-semibold">
                      {Number(sig.raw_score ?? 0).toFixed(1)}
                    </td>
                    <td className="p-2 text-right">
                      <button
                        onClick={() => handleDispatch(sig)}
                        disabled={dispatchingId === sig.id}
                        className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-[10px] font-semibold text-white shadow-sm hover:bg-emerald-500 transition-all disabled:opacity-50"
                      >
                        <SendHorizontal className="h-3 w-3" />
                        {dispatchingId === sig.id ? "Dispatching…" : "Execute"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {recentSignals.map((sig) => {
                const isLong =
                  sig.side.toUpperCase() === "LONG" || sig.side.toUpperCase() === "BUY";
                const failed =
                  sig.status.includes("FAILED") || sig.status.includes("BLOCKED") || sig.status.includes("EXCEEDED");
                return (
                  <tr key={`recent-${sig.id}`} className="bg-slate-950/40 text-slate-400 hover:bg-slate-900/40 transition-colors">
                    <td className="p-2 font-mono text-slate-600">—</td>
                    <td className="p-2">
                      <span className="block font-semibold text-slate-300">{sig.symbol}</span>
                      <span className="mt-0.5 inline-flex rounded border border-violet-500/20 bg-violet-500/5 px-1.5 py-0.5 text-[9px] font-semibold text-violet-300/70">
                        {producerLabel(sig.producer)}
                      </span>
                    </td>
                    <td className="p-2">
                      <span className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        isLong
                          ? "bg-emerald-500/5 text-emerald-400/70 border border-emerald-500/10"
                          : "bg-rose-500/5 text-rose-400/70 border border-rose-500/10"
                      }`}>
                        {isLong ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                        {sig.side}
                      </span>
                    </td>
                    <td className="p-2 font-mono text-[10px] text-slate-500">
                      {sig.rejection_reason ? (
                        <span title={sig.rejection_reason}>{sig.rejection_reason}</span>
                      ) : (
                        sig.target_strategy || "—"
                      )}
                    </td>
                    <td className="p-2 font-mono font-semibold text-slate-400">
                      {Number(sig.raw_score ?? 0).toFixed(1)}
                    </td>
                    <td className="p-2 text-right">
                      <span className={cn(
                        "inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold",
                        sig.status === "PROTECTED"
                          ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                          : failed
                            ? "border border-rose-500/30 bg-rose-500/10 text-rose-300"
                            : "border border-amber-500/30 bg-amber-500/10 text-amber-300"
                      )}>
                        {sig.status.replace(/_/g, " ")}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
