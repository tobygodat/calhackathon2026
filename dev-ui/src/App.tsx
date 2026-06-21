import { useCallback, useEffect, useState } from "react";
import { fetchStatus, offlineStatus } from "./api";
import { AlertFeedPanel } from "./components/AlertFeedPanel";
import { CapabilityPanel } from "./components/CapabilityPanel";
import { ConnectionsPanel } from "./components/ConnectionsPanel";
import { IntakeTestPanel } from "./components/IntakeTestPanel";
import { LabProfilePanel } from "./components/LabProfilePanel";
import { LedgerPanel } from "./components/LedgerPanel";
import { MetricCards } from "./components/MetricCards";
import { PipelinePanel } from "./components/PipelinePanel";
import { RedisSourcesPanel } from "./components/RedisSourcesPanel";
import { ScannerScorecardPanel } from "./components/ScannerScorecardPanel";
import { ServiceFlipGraph } from "./components/ServiceFlipGraph";
import { StatusDot } from "./components/StatusBadge";
import type { SystemStatus } from "./types";

const POLL_MS = 10_000;

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastAttempt, setLastAttempt] = useState<Date | null>(null);
  const [ledgerRefreshKey, setLedgerRefreshKey] = useState(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    const live = await fetchStatus();
    setStatus(live);
    setLastAttempt(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const offline = status === null;
  const view = status ?? offlineStatus();

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-8">
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <p className="text-xs uppercase tracking-widest text-cyan-500">
            Baskr · Dev Monitor
          </p>
          <h1 className="mt-1 text-xl font-semibold text-slate-100">
            Intake & integration status
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Sources · Redis · APIs · agent consumer
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <StatusDot status={offline ? "down" : view.healthy ? "healthy" : "down"} />
            <span className="text-sm text-slate-300">
              {offline ? "Backend offline" : view.healthy ? "System healthy" : "System degraded"}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-500">
            <span
              className={
                !offline
                  ? "rounded bg-emerald-500/15 px-2 py-0.5 text-emerald-400"
                  : "rounded bg-slate-500/15 px-2 py-0.5 text-slate-500"
              }
            >
              {!offline ? "Live API" : "Offline"}
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
        {/* System overview */}
        <MetricCards metrics={offline ? null : view.metrics} />
        <PipelinePanel metrics={offline ? null : view.metrics} />
        <ServiceFlipGraph metrics={offline ? null : view.metrics} />
        <CapabilityPanel status={offline ? null : view} />
        <ConnectionsPanel connections={view.connections} />

        {/* Lab data panel */}
        <LabProfilePanel />

        {/* Agent loop alert feed */}
        <AlertFeedPanel />

        {/* Infrastructure + intake + ledger */}
        <RedisSourcesPanel sources={view.redisSources} />
        <IntakeTestPanel onIngested={() => setLedgerRefreshKey((k) => k + 1)} />

        {/* Labeled-test scoring: how many the scanner gets right */}
        <ScannerScorecardPanel />

        <LedgerPanel refreshKey={ledgerRefreshKey} />
      </main>

      <footer className="mt-10 border-t border-slate-800 pt-4 text-xs text-slate-600">
        Polls <code className="text-slate-500">GET /status</code> every 10s via{" "}
        <code className="text-slate-500">/api/status</code> proxy. Set{" "}
        <code className="text-slate-500">VITE_STATUS_URL</code> to override.
      </footer>
    </div>
  );
}
