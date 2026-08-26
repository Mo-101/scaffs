import React, { useState, useEffect, useCallback } from "react";
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

export const SignalPriorityQueuePanel: React.FC = () => {
  const [pendingSignals, setPendingSignals] = useState<QueuedSignal[]>([]);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [dispatchingId, setDispatchingId] = useState<string | null>(null);

  const fetchPending = useCallback(async () => {
    try {
      const res = await api.getSignalQueuePending(30);
      if (res?.ok) setPendingSignals(res.signals || []);
    } catch (err) {
      console.error("Failed to load pending queue:", err);
    }
  }, []);

  useEffect(() => {
    void fetchPending();
    const interval = setInterval(() => void fetchPending(), 5000);
    return () => clearInterval(interval);
  }, [fetchPending]);

  const handleSyncIdim = async () => {
    setSyncing(true);
    try {
      const res = await api.syncIdimSignals({ auto_dispatch: false, notional_usd: 25.0 });
      if (res?.ok) {
        toast.success("Idim Ikang Feed Synced", {
          description: `Ingested ${res.enqueued_count} new retained-strategy signals into priority queue.`,
        });
        await fetchPending();
      }
    } catch (err: any) {
      toast.error("Idim Sync Error", { description: err?.message || String(err) });
    } finally {
      setSyncing(false);
    }
  };

  const handleDispatch = async (signal: QueuedSignal) => {
    setDispatchingId(signal.id);
    try {
      const res = await api.dispatchQueuedSignal({ queue_id: signal.id, notional_usd: 25.0 });
      if (res?.ok) {
        toast.success(`Dispatched ${signal.symbol} ${signal.side}`, {
          description: `Binance Testnet Order ID: ${res.order_id} (${res.client_order_id})`,
        });
        await fetchPending();
      } else {
        toast.error("Execution Blocked", { description: res?.reason || res?.error });
      }
    } catch (err: any) {
      toast.error("Dispatch Failed", { description: err?.message || String(err) });
    } finally {
      setDispatchingId(null);
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
              Idim Ikang Signal Queue &amp; Strategy Router
            </h2>
            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400 border border-emerald-500/20 leading-none">
              LIVE FEED ACTIVE
            </span>
          </div>
          <p className="text-[10px] text-slate-400 mt-0.5 hidden sm:block">
            Multi-criteria TOPSIS ranking · quality gating · collision-guarded execution · Binance USDⓈ-M
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
        <button
          onClick={handleSyncIdim}
          disabled={syncing}
          className="flex items-center gap-1.5 rounded-lg bg-amber-600/20 px-3 py-1.5 text-xs font-medium text-amber-300 border border-amber-500/30 hover:bg-amber-600/30 transition-all disabled:opacity-50 flex-shrink-0"
        >
          <RefreshCw className={`h-3 w-3 ${syncing ? "animate-spin" : ""}`} />
          {syncing ? "Syncing..." : "Sync Idim Stream"}
        </button>
      </div>

      {/* Active Priority Queue — scrollable, max 5 rows visible */}
      {pendingSignals.length === 0 ? (
        <div className="py-5 text-center text-xs text-slate-500">
          No pending signals. Click{" "}
          <span className="text-amber-400 font-semibold">"Sync Idim Stream"</span> to ingest fresh signals.
        </div>
      ) : (
        <div className="overflow-auto" style={{ maxHeight: "220px" }}>
          <table className="w-full text-left text-xs text-slate-300 min-w-[640px]">
            <thead className="sticky top-0 bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider z-10">
              <tr>
                <th className="p-2">Rank / TOPSIS</th>
                <th className="p-2">Symbol</th>
                <th className="p-2">Side</th>
                <th className="p-2">Strategy</th>
                <th className="p-2">Score</th>
                <th className="p-2 text-right">Execute</th>
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
                    <td className="p-2 font-bold text-white">{sig.symbol}</td>
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
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
