import { useState } from "react";
import { fetchSearch } from "../api";
import type { SearchHit } from "../types";
import { PaperCard } from "./PaperCard";

export function ActiveSearchPanel() {
  const [question, setQuestion] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setHits(null);
    const result = await fetchSearch(question.trim());
    if (result === null) {
      setError("Search failed — check that the backend is running.");
    } else {
      setHits(result);
    }
    setLoading(false);
  }

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Active Search
        <span className="ml-2 text-xs font-normal normal-case text-slate-600">
          POST /api/search → classify recent papers live
        </span>
      </h2>

      <form onSubmit={handleSearch} className="flex gap-2 mb-4">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. how does fiber affect gut microbiome diversity?"
          className="flex-1 rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded border border-cyan-700 bg-cyan-900/30 px-4 py-2 text-sm font-medium text-cyan-300 transition hover:bg-cyan-800/40 disabled:opacity-40"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

      {hits !== null && (
        <div className="space-y-3">
          {hits.length === 0 ? (
            <p className="text-xs text-slate-500">
              No relevant papers found (all classified NOT_RELEVANT or no papers fetched).
              Try seeding the profile and ingest first.
            </p>
          ) : (
            <>
              <p className="text-xs text-slate-500 mb-2">
                {hits.length} relevant paper{hits.length !== 1 ? "s" : ""} found
              </p>
              {hits.map((hit, i) => (
                <PaperCard
                  key={`${hit.paper.source_id}-${i}`}
                  paper={hit.paper}
                  classification={hit.classification}
                />
              ))}
            </>
          )}
        </div>
      )}
    </section>
  );
}
