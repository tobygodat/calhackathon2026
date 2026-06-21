import { useEffect, useState } from "react";
import { getDigest, getDigestHistory } from "../api";
import type { DigestEntry, DigestSummary } from "../types";
import LabelBadge from "./LabelBadge";
import PaperCard from "./PaperCard";

export default function DigestHistoryPanel() {
  const [history, setHistory] = useState<DigestSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<DigestEntry[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDigestHistory()
      .then((h) => {
        setHistory(h);
        if (h.length > 0) loadDate(h[0].date);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingHistory(false));
  }, []);

  function loadDate(date: string) {
    setSelected(date);
    setLoadingEntries(true);
    setEntries(null);
    getDigest(date)
      .then(setEntries)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoadingEntries(false));
  }

  return (
    <section className="rounded-lg border border-neutral-800 p-4 flex flex-col gap-4">
      <h2 className="font-medium">Daily Digest</h2>

      {error && (
        <p className="text-xs text-red-400 border border-red-900/50 rounded px-3 py-2 bg-red-950/30">
          {error}
        </p>
      )}

      {loadingHistory && (
        <p className="text-sm text-neutral-500 animate-pulse">Loading…</p>
      )}

      {!loadingHistory && history.length === 0 && (
        <p className="text-sm text-neutral-500">No digests available.</p>
      )}

      {history.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {history.map((s) => (
            <button
              key={s.date}
              type="button"
              onClick={() => loadDate(s.date)}
              className={`flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition ${
                selected === s.date
                  ? "border-neutral-600 bg-neutral-800 text-neutral-100"
                  : "border-neutral-800 text-neutral-400 hover:border-neutral-700 hover:text-neutral-200"
              }`}
            >
              <span>{s.date}</span>
              <span className="text-neutral-600">·</span>
              <LabelBadge label={s.top_label} />
              <span className="text-neutral-500">{s.count}</span>
            </button>
          ))}
        </div>
      )}

      {loadingEntries && (
        <p className="text-sm text-neutral-500 animate-pulse">Loading digest…</p>
      )}

      {entries && entries.length === 0 && (
        <p className="text-sm text-neutral-500">No relevant papers in this digest.</p>
      )}

      {entries && entries.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-neutral-500">
            {entries.length} paper{entries.length !== 1 ? "s" : ""} · {selected}
          </p>
          {entries.map((entry) => (
            <PaperCard
              key={`${entry.paper.source}:${entry.paper.source_id}`}
              paper={entry.paper}
              classification={entry.classification}
            />
          ))}
        </div>
      )}
    </section>
  );
}
