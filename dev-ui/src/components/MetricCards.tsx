import type { SystemMetrics } from "../types";
import { formatRelativeTime } from "./StatusBadge";

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
}

function MetricCard({ label, value, sub, highlight }: MetricCardProps) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        highlight
          ? "border-cyan-500/40 bg-cyan-500/5"
          : "border-slate-700/60 bg-slate-900/50"
      }`}
    >
      <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-100">
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function MetricCards({ metrics }: { metrics: SystemMetrics }) {
  const hitRate =
    metrics.langCacheHitRate != null
      ? `${Math.round(metrics.langCacheHitRate * 100)}%`
      : "—";

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">Metrics</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Files processed (1h)"
          value={metrics.filesProcessedLastHour}
          sub="Papers through agent loop"
          highlight
        />
        <MetricCard
          label="Connections healthy"
          value={`${metrics.connectionsHealthyPercent}%`}
          sub="All monitored services"
          highlight
        />
        <MetricCard
          label="Alerts fired (1h)"
          value={metrics.alertsFiredLastHour}
          sub="Proactive SSE alerts"
        />
        <MetricCard
          label="Corpus index docs"
          value={metrics.corpusIndexDocs.toLocaleString()}
          sub="RedisVL idx:baskr-corpus"
        />
        <MetricCard
          label="Stream queue"
          value={metrics.streamQueueLength}
          sub={`${metrics.streamPending} pending in consumer group`}
        />
        <MetricCard
          label="Memory records"
          value={metrics.memoryRecords}
          sub="Agent Memory LTM"
        />
        <MetricCard
          label="LangCache hit rate"
          value={hitRate}
          sub="Query panel cache"
        />
        <MetricCard
          label="Last processed"
          value={formatRelativeTime(metrics.lastProcessedAt)}
          sub={`Consumer heartbeat ${formatRelativeTime(metrics.consumerLastHeartbeat)}`}
        />
      </div>
    </section>
  );
}
