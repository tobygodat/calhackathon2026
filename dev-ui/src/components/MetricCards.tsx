import type { SystemMetrics } from "../types";
import { formatRelativeTime } from "./StatusBadge";

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  highlight?: boolean;
  pending?: boolean;
  descriptor?: string;
}

function MetricCard({
  label,
  value,
  sub,
  highlight,
  pending,
  descriptor,
}: MetricCardProps) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        highlight
          ? "border-cyan-500/40 bg-cyan-500/5"
          : "border-slate-700/60 bg-slate-900/50"
      }`}
    >
      {descriptor ? (
        <span
          className="group relative inline-block cursor-help text-xs uppercase tracking-wider text-slate-500"
          title={descriptor}
        >
          <span className="border-b border-dotted border-slate-600">{label}</span>
          <span
            className="pointer-events-none absolute left-0 top-full z-10 mt-1 w-56 rounded border border-slate-700 bg-slate-950/95 px-2.5 py-1.5 text-[11px] normal-case leading-snug tracking-normal text-slate-200 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100"
            role="tooltip"
          >
            {descriptor}
          </span>
        </span>
      ) : (
        <p className="text-xs uppercase tracking-wider text-slate-500">{label}</p>
      )}
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
          label="New papers / hr"
          value={m != null ? m.newPapersLastHour : "—"}
          sub="Current intake rate"
          descriptor="How many distinct new papers entered the ledger in the last 60 minutes — the current intake rate."
          highlight
          pending={m == null}
        />
        <MetricCard
          label="Since last new paper"
          value={m != null ? formatRelativeTime(m.lastNewPaperAt) : "—"}
          sub="Most recent first-seen"
          descriptor="Elapsed time since the most recent new paper was first seen. Long gaps suggest the intake stream has gone quiet."
          highlight
          pending={m == null}
        />
        <MetricCard
          label="Connections healthy"
          value={m != null ? `${m.connectionsHealthy}/${m.connectionsTotal}` : "—"}
          sub="healthy / total services"
          descriptor="Number of monitored integrations (data sources, Redis, external APIs) currently reporting healthy out of the total being checked."
          highlight
          pending={m == null}
        />
        <MetricCard
          label="Alerts fired (1h)"
          value={m != null ? m.alertsFiredLastHour : "—"}
          sub="Proactive SSE alerts"
          descriptor="How many proactive alerts the agent loop pushed over the SSE stream in the last 60 minutes."
          pending={m == null}
        />
        <MetricCard
          label="Corpus index docs"
          value={m != null ? m.corpusIndexDocs.toLocaleString() : "—"}
          sub="RedisVL idx:baskr-corpus"
          descriptor="Total documents currently indexed in the RedisVL corpus index that powers semantic retrieval."
          pending={m == null}
        />
        <MetricCard
          label="New papers seen"
          value={m != null ? m.newPapersSeen.toLocaleString() : "—"}
          sub="Distinct papers all-time"
          descriptor="Cumulative count of distinct papers the system has ever recorded in the ledger since startup."
          pending={m == null}
        />
        <MetricCard
          label="Stream queue"
          value={m != null ? m.streamQueueLength : "—"}
          sub={
            m != null
              ? `${m.streamPending} pending in consumer group`
              : "Pending in consumer group"
          }
          descriptor="Length of the intake stream queue and how many entries are still pending acknowledgement by the consumer group. Growth here means the consumer is falling behind."
          pending={m == null}
        />
        <MetricCard
          label="Memory records"
          value={m != null ? m.memoryRecords : "—"}
          sub="Agent Memory LTM"
          descriptor="Number of long-term memory records stored in Agent Memory that the agent can recall across sessions."
          pending={m == null}
        />
        <MetricCard
          label="LangCache hit rate"
          value={hitRate}
          sub="Semantic cache"
          descriptor="Fraction of LLM/query requests served from the LangCache semantic cache instead of recomputing — higher means more cost and latency saved."
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
          descriptor="When the consumer last finished processing an item, plus its most recent heartbeat. Stale values indicate the consumer may be stuck or down."
          pending={m == null}
        />
      </div>
    </section>
  );
}
