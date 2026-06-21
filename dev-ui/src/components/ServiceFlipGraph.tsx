import type { SystemMetrics } from "../types";

const PANEL_DESCRIPTOR =
  "Counts how many times each monitored service has transitioned between up and down, so you can compare which integrations are flapping most.";

export function ServiceFlipGraph({ metrics }: { metrics: SystemMetrics | null }) {
  const counts = metrics?.statusFlipCounts ?? {};
  const series = metrics?.statusFlipSeries ?? [];

  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const max = rows.reduce((acc, [, count]) => Math.max(acc, count), 0);

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
        <span
          className="group relative inline-block cursor-help"
          title={PANEL_DESCRIPTOR}
        >
          <span className="border-b border-dotted border-slate-600">
            Service uptime flips
          </span>
          <span
            className="pointer-events-none absolute left-0 top-full z-10 mt-1 w-64 rounded border border-slate-700 bg-slate-950/95 px-2.5 py-1.5 text-[11px] normal-case leading-snug tracking-normal text-slate-200 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100"
            role="tooltip"
          >
            {PANEL_DESCRIPTOR}
          </span>
        </span>
      </h2>

      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">No status changes recorded yet.</p>
      ) : (
        <>
          <div className="space-y-2.5">
            {rows.map(([service, count]) => {
              const pct = max > 0 ? Math.max(4, (count / max) * 100) : 0;
              return (
                <div key={service} className="flex items-center gap-3">
                  <span className="w-32 shrink-0 truncate text-xs text-slate-300">
                    {service}
                  </span>
                  <div className="h-4 flex-1 overflow-hidden rounded bg-slate-800/60">
                    <div
                      className="h-full rounded bg-cyan-500/60"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="w-8 shrink-0 text-right text-xs tabular-nums text-slate-400">
                    {count}
                  </span>
                </div>
              );
            })}
          </div>

          {series.length > 0 && (
            <div className="mt-5 border-t border-slate-800 pt-3">
              <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-600">
                Recent transitions (oldest → newest)
              </p>
              <div className="flex flex-wrap gap-0.5">
                {series.map((event, i) => (
                  <span
                    key={`${event.connection}-${event.changed_at}-${i}`}
                    title={`${event.connection} → ${event.transition} @ ${new Date(
                      event.changed_at,
                    ).toLocaleString()}`}
                    className={`h-3 w-1.5 rounded-sm ${
                      event.transition === "on" ? "bg-emerald-400/80" : "bg-red-400/80"
                    }`}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
