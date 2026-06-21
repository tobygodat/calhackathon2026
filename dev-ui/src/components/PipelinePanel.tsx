import { useState } from "react";
import { runPipelineSearch, type PipelineSearchResult } from "../api";
import type { SourceContact, SystemMetrics } from "../types";
import { StatusDot } from "./StatusBadge";

const SOURCE_LABELS: Record<string, string> = {
  pubmed: "PubMed / NCBI",
  arxiv: "arXiv",
  biorxiv: "bioRxiv",
  medrxiv: "medRxiv",
  openalex: "OpenAlex",
  chemrxiv: "ChemRxiv",
};

function fmtAge(seconds: number | null): string {
  if (seconds == null) return "no contact yet";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function fmtMinutes(seconds?: number): string {
  if (seconds == null) return "—";
  return `${Math.round(seconds / 60)} min`;
}

/** One of the two in-flight batches, with its current depth. */
function BatchCard({
  title,
  count,
  waitingFor,
  accent,
}: {
  title: string;
  count: number;
  waitingFor: string;
  accent: string;
}) {
  return (
    <div className={`rounded-lg border p-4 ${accent}`}>
      <p className="text-xs uppercase tracking-wider text-slate-500">{title}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums text-slate-100">
        {count.toLocaleString()}
      </p>
      <p className="mt-1 text-xs text-slate-500">{waitingFor}</p>
    </div>
  );
}

const STATE_META: Record<
  NonNullable<SourceContact["state"]>,
  { dot: "healthy" | "ready" | "down"; badge: string; label: string }
> = {
  stable: {
    dot: "healthy",
    badge: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300",
    label: "stable",
  },
  ready: {
    dot: "ready",
    badge: "border-indigo-500/40 bg-indigo-500/15 text-indigo-300",
    label: "ready",
  },
  stale: {
    dot: "down",
    badge: "border-amber-500/40 bg-amber-500/15 text-amber-300",
    label: "stale",
  },
  down: {
    dot: "down",
    badge: "border-red-500/40 bg-red-500/15 text-red-300",
    label: "down",
  },
};

/** A source's stable-connection row: dot + label + last-contact freshness. */
function SourceContactRow({
  source,
  contact,
}: {
  source: string;
  contact: SourceContact;
}) {
  const label = SOURCE_LABELS[source] ?? source;
  // Fall back to the boolean when the backend didn't send an explicit state.
  const state = contact.state ?? (contact.stable ? "stable" : "down");
  const meta = STATE_META[state];
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-3 py-2 last:border-b-0">
      <div className="flex min-w-0 items-center gap-2.5">
        <StatusDot status={meta.dot} />
        <span className="truncate text-sm text-slate-200">{label}</span>
        {contact.optional && (
          <span className="shrink-0 rounded border border-slate-600 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-500">
            best-effort
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 text-xs">
        <span className="tabular-nums text-slate-500">
          {state === "ready" && contact.age_seconds == null
            ? "standby"
            : fmtAge(contact.age_seconds)}
        </span>
        <span
          className={`rounded border px-1.5 py-0.5 uppercase tracking-wide ${meta.badge}`}
        >
          {meta.label}
        </span>
      </div>
    </div>
  );
}

export function PipelinePanel({ metrics }: { metrics: SystemMetrics | null }) {
  const m = metrics;
  const stage = m?.stageCounts ?? {};
  const contacts = m?.sourceContacts ?? {};
  const sources = Object.keys(contacts);

  const [query, setQuery] = useState("gut microbiome");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PipelineSearchResult | null>(null);

  async function onRun() {
    setBusy(true);
    setResult(await runPipelineSearch(query));
    setBusy(false);
  }

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">Live pipeline</h2>

      {/* The two in-flight batches */}
      <div className="grid gap-3 sm:grid-cols-2">
        <BatchCard
          title="Batch 1 · Vector-search queue"
          count={m?.batchVectorSearch ?? 0}
          waitingFor="Seen papers waiting to be vector searched"
          accent="border-sky-500/40 bg-sky-500/5"
        />
        <BatchCard
          title="Batch 2 · LLM-scan queue"
          count={m?.batchLlmScan ?? 0}
          waitingFor="Gate survivors waiting to be LLM scanned"
          accent="border-violet-500/40 bg-violet-500/5"
        />
      </div>

      {/* Stage throughput: seen -> passed gate -> scanned -> alerts */}
      <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-700/60 bg-slate-900/50 px-4 py-3 text-sm">
        <span className="text-slate-400">Seen</span>
        <span className="font-semibold tabular-nums text-slate-100">
          {stage.seen ?? 0}
        </span>
        <span className="text-slate-600">→</span>
        <span className="text-slate-400">Passed gate</span>
        <span className="font-semibold tabular-nums text-sky-300">
          {stage.vector_passed ?? 0}
        </span>
        <span className="text-slate-600">→</span>
        <span className="text-slate-400">LLM scanned</span>
        <span className="font-semibold tabular-nums text-violet-300">
          {stage.scanned ?? 0}
        </span>
        <span className="text-slate-600">→</span>
        <span className="text-slate-400">Alerts</span>
        <span className="font-semibold tabular-nums text-emerald-300">
          {stage.alerts_fired ?? 0}
        </span>
      </div>

      {/* Stable-connection model: per-source last-contact freshness */}
      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500">
            Source connections · stable = contact in {fmtMinutes(m?.stableWindowS)}
          </h3>
          <span className="text-xs text-slate-600">
            heartbeat every {fmtMinutes(m?.heartbeatIntervalS)} (staggered)
          </span>
        </div>
        {sources.length === 0 ? (
          <p className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4 text-sm text-slate-600">
            No source contacts reported yet.
          </p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-700/60 bg-slate-900/40">
            {sources.map((s) => (
              <SourceContactRow key={s} source={s} contact={contacts[s]} />
            ))}
          </div>
        )}
      </div>

      {/* Manual pipeline fetch — pull live papers across all sources on demand */}
      <div className="mt-4 rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="query (e.g. gut microbiome)"
            className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-slate-500"
          />
          <button
            type="button"
            onClick={onRun}
            disabled={busy || query.trim() === ""}
            className="rounded border border-cyan-600/50 bg-cyan-500/10 px-3 py-1.5 text-sm text-cyan-300 transition hover:border-cyan-500 disabled:opacity-50"
          >
            {busy ? "Fetching…" : "Fetch across sources"}
          </button>
        </div>
        {result && (
          <div className="mt-3 text-xs text-slate-400">
            <p className="text-slate-300">
              {result.papers.length} papers (deduped) ·{" "}
              {Object.entries(result.counts)
                .map(([s, c]) => `${s}:${c}`)
                .join("  ") || "no per-source counts"}
            </p>
            {Object.keys(result.errors).length > 0 && (
              <p className="mt-1 text-amber-400">
                {Object.entries(result.errors)
                  .map(([s, e]) => `${s}: ${e}`)
                  .join(" · ")}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
