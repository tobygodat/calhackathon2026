import type { ServiceConnection } from "../types";
import { StatusBadge, StatusDot } from "./StatusBadge";

// Category ordering + per-type color coding. Source = sky/cyan, redis = rose,
// api = violet. Each row carries a left accent + a small category tag.
const CATEGORY_ORDER: ServiceConnection["category"][] = ["source", "redis", "api"];

const CATEGORY_META: Record<
  ServiceConnection["category"],
  { label: string; accent: string; tag: string }
> = {
  source: {
    label: "Data source",
    accent: "border-l-sky-500/70",
    tag: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  },
  redis: {
    label: "Redis",
    accent: "border-l-rose-500/70",
    tag: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  },
  api: {
    label: "API",
    accent: "border-l-violet-500/70",
    tag: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  },
};

// Down/degraded services sort to the top within their category so problems pop.
// "ready" (best-effort standby) is not a fault, so it sorts down with healthy.
const STATUS_RANK: Record<ServiceConnection["status"], number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  ready: 3,
  healthy: 4,
};

function sortConnections(connections: ServiceConnection[]): ServiceConnection[] {
  return [...connections].sort((a, b) => {
    const cat =
      CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
    if (cat !== 0) return cat;
    const st = STATUS_RANK[a.status] - STATUS_RANK[b.status];
    if (st !== 0) return st;
    return a.label.localeCompare(b.label);
  });
}

function ConnectionRow({ conn }: { conn: ServiceConnection }) {
  const meta = CATEGORY_META[conn.category];
  return (
    <div
      className={`flex items-center justify-between gap-3 border-b border-l-2 border-slate-800 bg-slate-900/40 px-3 py-2.5 last:border-b-0 ${meta.accent}`}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <StatusDot status={conn.status} />
        <span className="truncate text-sm text-slate-200">{conn.label}</span>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${meta.tag}`}
        >
          {meta.label}
        </span>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {conn.latencyMs != null && (
          <span className="text-xs tabular-nums text-slate-500">
            {conn.latencyMs}ms
          </span>
        )}
        <StatusBadge status={conn.status} />
      </div>
    </div>
  );
}

export function ConnectionsPanel({
  connections,
}: {
  connections: ServiceConnection[];
}) {
  const sorted = sortConnections(connections);

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">Connections</h2>
      {sorted.length === 0 ? (
        <p className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4 text-sm text-slate-600">
          No services reported.
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-700/60">
          {sorted.map((conn) => (
            <ConnectionRow key={conn.id} conn={conn} />
          ))}
        </div>
      )}
    </section>
  );
}
