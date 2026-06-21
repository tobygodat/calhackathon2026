/**
 * PipelineMetricsPanel
 *
 * Displays per-source paper counts, dedupe efficiency, last-query context,
 * and per-source error flags sourced from the live /api/status endpoint or
 * from the most recent pipeline search result (whichever is fresher).
 *
 * Designed to sit between MetricCards and PipelinePanel in the dashboard.
 */

import type { PipelineSearchResult, SystemMetrics } from "../types";

// ─── Source display config ────────────────────────────────────────────────────

const SOURCE_META: Record<
  string,
  { label: string; color: string; dot: string }
> = {
  pubmed: {
    label: "PubMed / NCBI",
    color: "border-blue-500/40 bg-blue-500/10 text-blue-300",
    dot: "bg-blue-400",
  },
  arxiv: {
    label: "arXiv",
    color: "border-purple-500/40 bg-purple-500/10 text-purple-300",
    dot: "bg-purple-400",
  },
  biorxiv: {
    label: "bioRxiv / medRxiv",
    color: "border-amber-500/40 bg-amber-500/10 text-amber-300",
    dot: "bg-amber-400",
  },
};

function sourceMeta(id: string) {
  return (
    SOURCE_META[id] ?? {
      label: id,
      color: "border-slate-500/40 bg-slate-500/10 text-slate-300",
      dot: "bg-slate-400",
    }
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SourceCountRow({
  source,
  count,
  error,
}: {
  source: string;
  count: number;
  error?: string;
}) {
  const meta = sourceMeta(source);
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-800 py-2.5 last:border-0">
      <div className="flex min-w-0 items-center gap-2">
        <span
          className={`inline-block h-2 w-2 shrink-0 rounded-full ${
            error ? "bg-red-400" : meta.dot
          }`}
        />
        <span className="truncate text-sm text-slate-300">{meta.label}</span>
        {error && (
          <span
            className="max-w-[12rem] truncate text-xs text-red-400"
            title={error}
          >
            {error}
          </span>
        )}
      </div>
      <span
        className={`shrink-0 rounded border px-2 py-0.5 text-xs tabular-nums ${
          error
            ? "border-red-500/40 bg-red-500/10 text-red-400"
            : meta.color
        }`}
      >
        {error ? "error" : `${count} papers`}
      </span>
    </div>
  );
}

function DedupeGauge({ ratio }: { ratio: number }) {
  // ratio = fraction removed by dedup (0 = no dups, 1 = all were dups)
  const pct = Math.round(ratio * 100);
  const barColor =
    pct === 0
      ? "bg-slate-600"
      : pct < 15
      ? "bg-emerald-500"
      : pct < 40
      ? "bg-amber-500"
      : "bg-red-500";

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-500">Dedupe removed</span>
        <span className="tabular-nums text-slate-300">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-slate-600">
        {pct === 0
          ? "No duplicates detected"
          : `${pct}% of raw papers collapsed across sources`}
      </p>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

interface PipelineMetricsPanelProps {
  /** Live metrics from the /api/status poll (may carry pipeline_source_counts etc.) */
  metrics: SystemMetrics | null;
  /** Most recent search result from PipelinePanel — overrides metrics when present */
  lastResult: PipelineSearchResult | null;
  /** The query string that produced lastResult */
  lastQuery: string;
}

export function PipelineMetricsPanel({
  metrics,
  lastResult,
  lastQuery,
}: PipelineMetricsPanelProps) {
  // Prefer the freshest search result; fall back to status-endpoint metrics
  const sourceCounts: Record<string, number> =
    lastResult?.counts ?? metrics?.pipelineSourceCounts ?? {};

  const sourceErrors: Record<string, string> =
    lastResult?.errors ?? metrics?.pipelineSourceErrors ?? {};

  const totalRaw = Object.values(sourceCounts).reduce((s, n) => s + n, 0);
  const totalDeduped = lastResult?.papers.length ?? metrics?.pipelineLastResultCount;
  const hasData = totalRaw > 0 || Object.keys(sourceErrors).length > 0;

  const dedupeRatio =
    lastResult != null && totalRaw > 0
      ? (totalRaw - (lastResult.papers.length ?? 0)) / totalRaw
      : (metrics?.pipelineDedupeRatio ?? null);

  const activeQuery = lastQuery || metrics?.pipelineLastQuery;

  // All known source names (union of counts + errors keys)
  const knownSources = [
    ...new Set([
      ...Object.keys(sourceCounts),
      ...Object.keys(sourceErrors),
    ]),
  ].filter((s) => s !== "request"); // exclude generic "request" error key

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">
        Pipeline health
      </h2>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* ── Per-source counts ── */}
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
          <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
            Per-source results
          </h3>

          {!hasData ? (
            <p className="text-sm text-slate-600">
              No results yet — run a pipeline search below.
            </p>
          ) : (
            knownSources.map((src) => (
              <SourceCountRow
                key={src}
                source={src}
                count={sourceCounts[src] ?? 0}
                error={sourceErrors[src]}
              />
            ))
          )}

          {hasData && (
            <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-500">
              <span>Total raw</span>
              <span className="tabular-nums text-slate-300">
                {totalRaw} papers
              </span>
            </div>
          )}
        </div>

        {/* ── Dedupe efficiency ── */}
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
            Deduplication
          </h3>

          {dedupeRatio != null ? (
            <div className="space-y-4">
              <DedupeGauge ratio={dedupeRatio} />
              {totalDeduped != null && (
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Raw fetched</span>
                    <span className="tabular-nums text-slate-300">
                      {totalRaw}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">After dedupe</span>
                    <span className="tabular-nums text-slate-300">
                      {totalDeduped}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Collapsed</span>
                    <span className="tabular-nums text-slate-400">
                      {totalRaw - totalDeduped}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              Run a multi-source search to see cross-source deduplication stats.
            </p>
          )}
        </div>

        {/* ── Last query context ── */}
        <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
            Last query
          </h3>

          {activeQuery ? (
            <div className="space-y-3">
              <p className="break-words text-sm font-medium text-slate-200">
                &ldquo;{activeQuery}&rdquo;
              </p>

              {totalDeduped != null && (
                <div className="rounded border border-slate-700 bg-slate-800/60 px-3 py-2">
                  <p className="text-xs text-slate-500">Unique results</p>
                  <p className="mt-0.5 text-xl font-semibold tabular-nums text-slate-100">
                    {totalDeduped}
                  </p>
                </div>
              )}

              {Object.keys(sourceErrors).filter((k) => k !== "request").length >
                0 && (
                <div className="rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
                  <span className="font-medium">
                    {
                      Object.keys(sourceErrors).filter((k) => k !== "request")
                        .length
                    }{" "}
                    source error
                    {Object.keys(sourceErrors).filter((k) => k !== "request")
                      .length !== 1
                      ? "s"
                      : ""}
                  </span>{" "}
                  — others succeeded
                </div>
              )}

              {sourceErrors["request"] && (
                <div className="rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
                  Request failed: {sourceErrors["request"]}
                </div>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              No queries run yet in this session.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
