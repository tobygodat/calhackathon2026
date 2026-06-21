import { useRef, useState } from "react";
import { runIntakeTest } from "../api";
import type { Label, ScorecardResult } from "../types";
import { LabelBadge } from "./LabelBadge";

const KNOWN_LABELS: Label[] = [
  "ANSWERS",
  "CONTRADICTS",
  "EXTENDS",
  "NOT_RELEVANT",
  "SCOOP",
];

function asLabel(value: string): Label {
  return (KNOWN_LABELS as string[]).includes(value)
    ? (value as Label)
    : "NOT_RELEVANT";
}

function accuracyColor(pct: number): string {
  if (pct >= 0.85) return "text-emerald-300";
  if (pct >= 0.6) return "text-amber-300";
  return "text-red-300";
}

export function ScannerScorecardPanel() {
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<ScorecardResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function submit(files: File[]) {
    if (files.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    const res = await runIntakeTest(files);
    if (res) {
      setCard(res);
    } else {
      setError(
        "Scoring run failed — check the backend is reachable and the file is the labeled testset.json.",
      );
    }
    setBusy(false);
  }

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files ? Array.from(e.target.files) : [];
    void submit(files);
    e.target.value = "";
  }

  const pct = card?.accuracy ?? null;

  return (
    <section className="rounded-lg border border-cyan-700/40 bg-slate-900 p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-cyan-300">
            Scanner scorecard
          </h2>
          <p className="mt-1 max-w-xl text-xs text-slate-500">
            Upload the labeled <code className="text-slate-400">testset.json</code>{" "}
            (synthetic papers tagged with the label the scanner{" "}
            <em>should</em> assign). Each paper runs through the real classifier
            and is scored against its ground-truth flag.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="rounded border border-cyan-600/60 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-200 transition hover:border-cyan-400 hover:bg-cyan-500/20 disabled:opacity-50"
          >
            {busy ? "Scoring…" : "Run labeled test"}
          </button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".json,application/json"
            onChange={handleSelect}
            className="hidden"
          />
        </div>
      </div>

      {error && <p className="mb-3 text-xs text-amber-400">{error}</p>}

      {!card && !error && (
        <p className="rounded border border-dashed border-slate-700 bg-slate-900/40 px-4 py-6 text-center text-xs text-slate-600">
          No test run yet. Click <span className="text-slate-400">Run labeled test</span>{" "}
          and pick{" "}
          <code className="text-slate-500">
            baskr/data/synthetic_intake/testset.json
          </code>
          .
        </p>
      )}

      {card && (
        <div className="space-y-5">
          {/* Headline scoreboard */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded border border-slate-700 bg-slate-800/60 p-3 text-center">
              <p
                className={`text-3xl font-bold tabular-nums ${
                  pct === null ? "text-slate-400" : accuracyColor(pct)
                }`}
              >
                {pct === null ? "—" : `${Math.round(pct * 100)}%`}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                accuracy
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/60 p-3 text-center">
              <p className="text-3xl font-bold tabular-nums text-emerald-300">
                {card.correct}
                <span className="text-base text-slate-500">/{card.labeled}</span>
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                correct
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/60 p-3 text-center">
              <p className="text-3xl font-bold tabular-nums text-red-300">
                {card.labeled - card.correct}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                missed
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/60 p-3 text-center">
              <p className="text-3xl font-bold tabular-nums text-slate-300">
                {card.total}
              </p>
              <p className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                papers scored
              </p>
            </div>
          </div>

          {card.degraded && (
            <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
              Backend has no ANTHROPIC_API_KEY — scored with the deterministic
              degraded classifier, not Claude.
            </p>
          )}

          {/* Confusion matrix: expected (rows) vs predicted (cols) */}
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-500">
              Confusion · rows = expected, cols = predicted
            </p>
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-xs">
                <thead>
                  <tr>
                    <th className="px-2 py-1 text-left text-slate-600">exp \ pred</th>
                    {card.labels.map((l) => (
                      <th key={l} className="px-2 py-1 text-center">
                        <LabelBadge label={asLabel(l)} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {card.labels.map((exp) => (
                    <tr key={exp} className="border-t border-slate-800">
                      <td className="px-2 py-1">
                        <LabelBadge label={asLabel(exp)} />
                      </td>
                      {card.labels.map((pred) => {
                        const n = card.confusion[exp]?.[pred] ?? 0;
                        const onDiag = exp === pred;
                        return (
                          <td
                            key={pred}
                            className={`px-2 py-1 text-center tabular-nums ${
                              n === 0
                                ? "text-slate-700"
                                : onDiag
                                  ? "font-semibold text-emerald-300"
                                  : "font-semibold text-red-300"
                            }`}
                          >
                            {n || "·"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Per-paper results */}
          <div>
            <p className="mb-2 text-[10px] uppercase tracking-wider text-slate-500">
              Per-paper results
            </p>
            <div className="space-y-1">
              {card.results.map((r, i) => (
                <div
                  key={i}
                  className={`flex flex-wrap items-center gap-2 rounded border px-3 py-2 text-xs ${
                    r.correct
                      ? "border-emerald-500/20 bg-emerald-500/5"
                      : "border-red-500/25 bg-red-500/5"
                  }`}
                >
                  <span
                    className={`text-sm ${
                      r.correct ? "text-emerald-400" : "text-red-400"
                    }`}
                    title={r.correct ? "correct" : "wrong"}
                  >
                    {r.correct ? "✓" : "✗"}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-slate-300" title={r.title}>
                    {r.title}
                  </span>
                  {r.expected_category && (
                    <span className="hidden text-[10px] text-slate-600 sm:inline">
                      {r.expected_category}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    {r.expected_label && (
                      <LabelBadge label={asLabel(r.expected_label)} />
                    )}
                    <span className="text-slate-600">→</span>
                    <LabelBadge label={asLabel(r.predicted_label)} />
                  </span>
                  <span className="w-10 text-right tabular-nums text-slate-500">
                    {Math.round(r.confidence * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>

          {Object.keys(card.errors).length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-slate-600">
                Errors
              </p>
              {Object.entries(card.errors).map(([file, msg]) => (
                <p
                  key={file}
                  className="rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs text-red-300"
                >
                  <span className="font-mono">{file}</span>: {msg}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
