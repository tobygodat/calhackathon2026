import { useState } from "react";
import { fetchPipeline } from "../api";
import type { Paper, PipelineSearchResult, PipelineSource } from "../types";

// WARNING: NATURE SOURCE IS DISABLED — DO NOT RE-ENABLE WITHOUT EXPLICIT REQUEST
const ALL_SOURCES: { id: PipelineSource; label: string }[] = [
  { id: "pubmed", label: "PubMed / NCBI" },
  { id: "arxiv", label: "arXiv" },
  { id: "biorxiv", label: "bioRxiv / medRxiv" },
  // { id: "nature", label: "Nature / Springer" },  // DISABLED
];

const DAY_OPTIONS = [1, 3, 7, 14, 30];

const SOURCE_COLORS: Record<PipelineSource, string> = {
  pubmed: "bg-blue-500/20 text-blue-400 border-blue-500/40",
  arxiv: "bg-purple-500/20 text-purple-400 border-purple-500/40",
  biorxiv: "bg-amber-500/20 text-amber-400 border-amber-500/40",
  // nature: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",  // DISABLED
};

function SourceBadge({ source }: { source: PipelineSource }) {
  const label = ALL_SOURCES.find((s) => s.id === source)?.label ?? source;
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs ${SOURCE_COLORS[source]}`}
    >
      {label}
    </span>
  );
}

function PaperCard({ paper }: { paper: Paper }) {
  const [expanded, setExpanded] = useState(false);
  const abstract = paper.abstract?.trim();
  const truncated = abstract && abstract.length > 280;

  return (
    <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
      <div className="mb-1.5 flex flex-wrap items-start justify-between gap-2">
        <h4 className="flex-1 text-sm font-medium leading-snug text-slate-100">
          {paper.url ? (
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-cyan-400 hover:underline"
            >
              {paper.title}
            </a>
          ) : (
            paper.title
          )}
        </h4>
        <SourceBadge source={paper.source} />
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500">
        {paper.published && <span>{paper.published}</span>}
        {paper.journal && <span className="truncate">{paper.journal}</span>}
        {paper.authors.length > 0 && (
          <span className="truncate">
            {paper.authors.slice(0, 3).join(", ")}
            {paper.authors.length > 3 ? ` +${paper.authors.length - 3}` : ""}
          </span>
        )}
        {paper.doi && (
          <a
            href={`https://doi.org/${paper.doi}`}
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-cyan-400 hover:underline"
          >
            DOI
          </a>
        )}
      </div>

      {abstract && (
        <p className="text-xs leading-relaxed text-slate-400">
          {expanded || !truncated ? abstract : `${abstract.slice(0, 280)}…`}
          {truncated && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="ml-1 text-cyan-500 hover:text-cyan-300"
            >
              {expanded ? "less" : "more"}
            </button>
          )}
        </p>
      )}

      {paper.categories.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {paper.categories.slice(0, 5).map((cat) => (
            <span
              key={cat}
              className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500"
            >
              {cat}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CountsRow({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-500">
      {entries.map(([src, n]) => (
        <span key={src}>
          <span className="font-medium text-slate-300">{n}</span> {src}
        </span>
      ))}
    </div>
  );
}

interface PipelinePanelProps {
  /** Called after each completed search with the query string and its result. */
  onResult?: (query: string, result: PipelineSearchResult) => void;
}

export function PipelinePanel({ onResult }: PipelinePanelProps) {
  const [query, setQuery] = useState("");
  const [days, setDays] = useState(7);
  const [selectedSources, setSelectedSources] = useState<Set<PipelineSource>>(
    new Set(ALL_SOURCES.map((s) => s.id)),
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PipelineSearchResult | null>(null);

  function toggleSource(id: PipelineSource) {
    setSelectedSources((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id); // keep at least one
      } else {
        next.add(id);
      }
      return next;
    });
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setResult(null);
    const res = await fetchPipeline({
      query: query.trim(),
      days,
      sources: [...selectedSources],
    });
    if (res) {
      setResult(res);
      onResult?.(query.trim(), res);
    }
    setLoading(false);
  }

  const hasErrors = result && Object.keys(result.errors).length > 0;

  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">
        Pipeline search
      </h2>
      <div className="rounded-lg border border-slate-700/60 bg-slate-900/50 p-4">
        <form onSubmit={handleSearch} className="space-y-4">
          {/* Query input */}
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. gut microbiome immunotherapy"
              className="min-w-0 flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/30"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="rounded border border-cyan-600/60 bg-cyan-600/20 px-4 py-1.5 text-sm text-cyan-300 transition hover:bg-cyan-600/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </div>

          {/* Options row */}
          <div className="flex flex-wrap items-center gap-4">
            {/* Days */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">Last</span>
              <div className="flex gap-1">
                {DAY_OPTIONS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDays(d)}
                    className={`rounded px-2 py-0.5 text-xs transition ${
                      days === d
                        ? "bg-cyan-600/30 text-cyan-300 border border-cyan-600/50"
                        : "border border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>

            {/* Sources */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">Sources:</span>
              {ALL_SOURCES.map((src) => (
                <label
                  key={src.id}
                  className="flex cursor-pointer items-center gap-1.5 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selectedSources.has(src.id)}
                    onChange={() => toggleSource(src.id)}
                    className="h-3 w-3 accent-cyan-500"
                  />
                  <span
                    className={
                      selectedSources.has(src.id)
                        ? "text-slate-300"
                        : "text-slate-600"
                    }
                  >
                    {src.label}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </form>

        {/* Results */}
        {result && (
          <div className="mt-5 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-4">
              <span className="text-sm text-slate-400">
                {result.papers.length === 0
                  ? "No papers found"
                  : `${result.papers.length} paper${result.papers.length !== 1 ? "s" : ""}`}
              </span>
              <CountsRow counts={result.counts} />
            </div>

            {hasErrors && (
              <div className="rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
                <span className="font-medium">Source errors: </span>
                {Object.entries(result.errors)
                  .map(([src, msg]) => `${src}: ${msg}`)
                  .join(" · ")}
              </div>
            )}

            <div className="space-y-3">
              {result.papers.map((paper) => (
                <PaperCard
                  key={`${paper.source}:${paper.source_id}`}
                  paper={paper}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
