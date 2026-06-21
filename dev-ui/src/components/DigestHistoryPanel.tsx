import { useEffect, useState } from "react";
import { fetchDigest, fetchDigestHistory } from "../api";
import type { DigestEntry, DigestSummary } from "../types";
import { LabelBadge } from "./LabelBadge";
import { PaperCard } from "./PaperCard";

function SummaryRow({
  summary,
  selected,
  onClick,
}: {
  summary: DigestSummary;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm transition ${
        selected
          ? "bg-slate-700 text-slate-100"
          : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
      }`}
    >
      <span className="font-mono">{summary.date}</span>
      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-500">{summary.count} hits</span>
        <LabelBadge label={summary.top_label} />
      </div>
    </button>
  );
}

export function DigestHistoryPanel() {
  const [history, setHistory] = useState<DigestSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<DigestEntry[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [loadingEntries, setLoadingEntries] = useState(false);

  useEffect(() => {
    fetchDigestHistory()
      .then(setHistory)
      .finally(() => setLoadingHistory(false));
  }, []);

  async function handleSelect(date: string) {
    if (selected === date) {
      setSelected(null);
      setEntries(null);
      return;
    }
    setSelected(date);
    setLoadingEntries(true);
    const result = await fetchDigest(date);
    setEntries(result);
    setLoadingEntries(false);
  }

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Digest History
        <span className="ml-2 text-xs font-normal normal-case text-slate-600">
          GET /api/digest/history · click a date to load entries
        </span>
      </h2>

      {loadingHistory && <p className="text-xs text-slate-500">Loading history…</p>}

      {history !== null && history.length === 0 && (
        <p className="text-xs text-slate-500">
          No frozen digests yet. Run <code>python scripts/freeze_digest.py</code>.
        </p>
      )}

      {history && history.length > 0 && (
        <div className="space-y-1 mb-4">
          {history.map((s) => (
            <SummaryRow
              key={s.date}
              summary={s}
              selected={selected === s.date}
              onClick={() => handleSelect(s.date)}
            />
          ))}
        </div>
      )}

      {selected && (
        <div className="border-t border-slate-800 pt-4 space-y-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
            {selected}
          </p>
          {loadingEntries && (
            <p className="text-xs text-slate-500">Loading entries…</p>
          )}
          {entries !== null && entries.length === 0 && (
            <p className="text-xs text-slate-500">No relevant papers in this digest.</p>
          )}
          {entries &&
            entries.map((entry, i) => (
              <PaperCard
                key={`${entry.paper.source_id}-${i}`}
                paper={entry.paper}
                classification={entry.classification}
              />
            ))}
        </div>
      )}
    </section>
  );
}
