import type { SystemMetrics } from "../types";
import { formatRelativeTime } from "./StatusBadge";

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
  pending?: boolean;
}

function MetricCard({ label, value, sub, highlight, pending }: MetricCardProps) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        highlight
          ? "border-cyan-500/40 bg-cyan-500/5"
          : "border-slate-700/60 bg-slate-900/50"
      }`}
    >
      <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          pending ? "text-slate-600" : "text-slate-100"
        }`}
      >
        {value}
      </p>
      {sub && (
        <p className={`mt-1 text-xs ${pending ? "text-slate-700" : "text-slate-500"}`}>
          {sub}
        </p>
      )}
    </div>
  );
}

export function MetricCards({ metrics }: { metrics: SystemMetrics | null }) {
  const m = metrics;

  const hitRate =
    m?.langCacheHitRate != null
      ? `${Math.round(m.langCacheHitRate * 100)}%`
      : "—";

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">Metrics</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Files processed (1h)"
          value={m != null ? m.filesProcessedLastHour : "—"}
          sub="Papers through agent loop"
          highlight
          pending={m == null}
        />
        <MetricCard
          label="Connections healthy"
          value={m != null ? `${m.connectionsHealthy}/${m.connectionsTotal}` : "—"}
          sub="healthy / total services"
          highlight
          pending={m == null}
        />
        <MetricCard
          label="Alerts fired (1h)"
          value={m != null ? m.alertsFiredLastHour : "—"}
          sub="Proactive SSE alerts"
          pending={m == null}
        />
        <MetricCard
          label="Corpus index docs"
          value={m != null ? m.corpusIndexDocs.toLocaleString() : "—"}
          sub="RedisVL idx:baskr-corpus"
          pending={m == null}
        />
        <MetricCard
          label="New papers seen"
          value={m != null ? m.newPapersSeen.toLocaleString() : "—"}
          sub="Distinct papers via pipeline"
          pending={m == null}
        />
        <MetricCard
          label="Stream queue"
          value={m != null ? m.streamQueueLength : "—"}
          sub={m != null ? `${m.streamPending} pending in consumer group` : "Pending in consumer group"}
          pending={m == null}
        />
        <MetricCard
          label="Memory records"
          value={m != null ? m.memoryRecords : "—"}
          sub="Agent Memory LTM"
          pending={m == null}
        />
        <MetricCard
          label="LangCache hit rate"
          value={hitRate}
          sub="Query panel cache"
          pending={m == null}
        />
        <MetricCard
          label="Last processed"
          value={m != null ? formatRelativeTime(m.lastProcessedAt) : "—"}
          sub={
            m != null
              ? `Consumer heartbeat ${formatRelativeTime(m.consumerLastHeartbeat)}`
              : "Consumer heartbeat"
          }
          pending={m == null}
        />
      </div>
    </section>
  );
}
