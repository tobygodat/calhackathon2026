import { useState } from "react";
import { search } from "../api";
import type { SearchHit } from "../types";
import PaperCard from "./PaperCard";

export default function ActiveSearchPanel() {
  const [question, setQuestion] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setHits(null);
    try {
      const results = await search(question.trim());
      setHits(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-4 flex flex-col gap-4">
      <h2 className="font-medium">Active Search</h2>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. fiber and T-cell regulation"
          className="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 placeholder-neutral-600 outline-none focus:border-cyan-600/60 focus:ring-1 focus:ring-cyan-600/30"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded border border-cyan-700/60 bg-cyan-700/20 px-4 py-1.5 text-sm text-cyan-300 transition hover:bg-cyan-700/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <p className="text-xs text-red-400 border border-red-900/50 rounded px-3 py-2 bg-red-950/30">
          {error}
        </p>
      )}

      {hits !== null && hits.length === 0 && !loading && (
        <p className="text-sm text-neutral-500">No relevant papers found.</p>
      )}

      {hits && hits.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-neutral-500">
            {hits.length} relevant paper{hits.length !== 1 ? "s" : ""} · live PubMed
          </p>
          {hits.map((hit) => (
            <PaperCard
              key={`${hit.paper.source}:${hit.paper.source_id}`}
              paper={hit.paper}
              classification={hit.classification}
            />
          ))}
        </div>
      )}
    </section>
  );
}
