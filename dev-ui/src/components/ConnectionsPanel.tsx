import type { ServiceConnection } from "../types";
import { StatusBadge, StatusDot } from "./StatusBadge";

const CATEGORY_LABELS: Record<ServiceConnection["category"], string> = {
  source: "Data sources",
  redis: "Redis integrations",
  api: "External APIs",
};

function ConnectionRow({ conn }: { conn: ServiceConnection }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-800 py-2.5 last:border-0">
      <div className="flex min-w-0 items-center gap-2">
        <StatusDot status={conn.status} />
        <span className="truncate text-sm text-slate-200">{conn.label}</span>
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
  const categories: ServiceConnection["category"][] = ["source", "redis", "api"];

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">Connections</h2>
      <div className="grid gap-4 lg:grid-cols-3">
        {categories.map((cat) => {
          const items = connections.filter((c) => c.category === cat);
          return (
            <div
              key={cat}
              className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4"
            >
              <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                {CATEGORY_LABELS[cat]}
              </h3>
              {items.length === 0 ? (
                <p className="text-sm text-slate-600">No services configured</p>
              ) : (
                items.map((conn) => (
                  <ConnectionRow key={conn.id} conn={conn} />
                ))
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
