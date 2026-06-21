import { useCallback, useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { ConnectionsPanel } from "./components/ConnectionsPanel";
import { MetricCards } from "./components/MetricCards";
import { PipelinePanel } from "./components/PipelinePanel";
import { RedisSourcesPanel } from "./components/RedisSourcesPanel";
import { StatusDot } from "./components/StatusBadge";
import type { SystemStatus } from "./types";

const POLL_MS = 10_000;

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 py-20 text-center">
      <div className="mb-3 h-3 w-3 rounded-full bg-slate-600" />
      <p className="text-sm font-medium text-slate-400">Awaiting backend</p>
      <p className="mt-1 max-w-xs text-xs text-slate-600">
        No data yet. Start the FastAPI service and ensure{" "}
        <code className="text-slate-500">GET /status</code> is reachable via{" "}
        <code className="text-slate-500">/api/status</code>.
      </p>
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastAttempt, setLastAttempt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const live = await fetchStatus();
    if (live) setStatus(live);
    setLastAttempt(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const isLive = status?.source === "live";

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-8">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <p className="text-xs uppercase tracking-widest text-cyan-500">
            Baskr · Dev Monitor
          </p>
          <h1 className="mt-1 text-xl font-semibold text-slate-100">
            Pipeline & integration status
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Sources · Redis · APIs · agent consumer
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <StatusDot status={status ? (status.healthy ? "healthy" : "down") : "unknown"} />
            <span className="text-sm text-slate-300">
              {status ? (status.healthy ? "System healthy" : "System degraded") : "No connection"}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span
              className={
                isLive
                  ? "rounded bg-emerald-500/15 px-2 py-0.5 text-emerald-400"
                  : "rounded bg-slate-500/15 px-2 py-0.5 text-slate-500"
              }
            >
              {isLive ? "Live API" : "No data"}
            </span>
            {lastAttempt && (
              <span>Last attempt {lastAttempt.toLocaleTimeString()}</span>
            )}
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="rounded border border-slate-700 px-2 py-0.5 text-slate-400 transition hover:border-slate-500 hover:text-slate-200 disabled:opacity-50"
            >
              {loading ? "…" : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      <main className="space-y-8">
        {status ? (
          <>
            <MetricCards metrics={status.metrics} />
            <ConnectionsPanel connections={status.connections} />
            <RedisSourcesPanel sources={status.redisSources} />
            <PipelinePanel />
          </>
        ) : (
          <EmptyState />
        )}
      </main>

      <footer className="mt-10 border-t border-slate-800 pt-4 text-xs text-slate-600">
        Polls <code className="text-slate-500">GET /status</code> every 10s via{" "}
        <code className="text-slate-500">/api/status</code> proxy. Set{" "}
        <code className="text-slate-500">VITE_STATUS_URL</code> to override.
      </footer>
    </div>
  );
}
