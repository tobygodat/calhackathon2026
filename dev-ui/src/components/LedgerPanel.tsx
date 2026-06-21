import { useEffect, useState } from "react";
import { fetchLedger } from "../api";
import type { LedgerEntry } from "../types";
import { formatRelativeTime } from "./StatusBadge";

export function LedgerPanel({ refreshKey }: { refreshKey: number }) {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchLedger()
      .then((data) => {
        if (!cancelled) setEntries(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const count = entries?.length ?? 0;

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Paper ledger
        {entries != null && (
          <span className="ml-1 text-xs font-normal normal-case text-slate-600">
            {count} {count === 1 ? "paper" : "papers"}
          </span>
        )}
        {loading && (
          <span className="ml-auto text-xs font-normal normal-case text-slate-600">
            loading…
          </span>
        )}
      </h2>

      {entries == null && loading ? (
        <p className="text-xs text-slate-500">Loading ledger…</p>
      ) : count === 0 ? (
        <p className="text-xs text-slate-500">
          No papers in the ledger yet — drop files via the intake tester above.
        </p>
      ) : (
        <div className="overflow-hidden rounded border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-[10px] uppercase tracking-wider text-slate-600">
                <th className="px-3 py-2 font-medium">Title</th>
                <th className="w-28 px-3 py-2 font-medium">Source</th>
                <th className="w-28 px-3 py-2 font-medium">First seen</th>
              </tr>
            </thead>
            <tbody>
              {entries!.map((entry, i) => (
                <tr
                  key={`${entry.title}-${entry.first_seen_at}-${i}`}
                  className="border-b border-slate-800/60 last:border-b-0"
                >
                  <td className="px-3 py-2 text-slate-200">{entry.title}</td>
                  <td className="px-3 py-2 text-xs uppercase tracking-wide text-slate-500">
                    {entry.source}
                  </td>
                  <td className="px-3 py-2 text-xs tabular-nums text-slate-500">
                    {formatRelativeTime(entry.first_seen_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
