// Flagged Papers — a database-style view of every paper across all digests.
// Pulls the full digest history, flattens it into one table, and lets the user
// filter by classification label or search the title/authors. Rows reuse the
// dashboard's click-to-expand animation. Same dark monochrome theme as the rest
// of the app.
import { useEffect, useMemo, useState } from "react";
import { getDigest, getDigestHistory } from "../../api";
import type { DigestEntry, Label } from "../../types";
import { LABEL_STYLES } from "../../labelStyles";
import TopNav from "../welcome/TopNav";
import PaperExpandModal from "../welcome/PaperExpandModal";

// Filter order — "all" first, then every flaggable label. NOT_RELEVANT is kept
// out of the quick filters but still searchable / shown under "All".
const FILTERS: { key: Label | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "CONTRADICTS", label: "Contradicts" },
  { key: "EXTENDS", label: "Extends" },
  { key: "ANSWERS", label: "Answers" },
  { key: "SCOOP", label: "Scoop" },
];

function authorLabel(entry: DigestEntry): string {
  const { authors, journal, source } = entry.paper;
  if (authors.length === 0) return journal ?? source;
  return authors.length > 1 ? `${authors[0]} et al.` : authors[0];
}

export default function FlaggedPapersPage() {
  const [entries, setEntries] = useState<DigestEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Label | "all">("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<{
    entry: DigestEntry;
    rect: DOMRect;
  } | null>(null);

  // Fetch every digest and flatten into a single newest-first list.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const history = await getDigestHistory();
        const all = await Promise.all(history.map((h) => getDigest(h.date)));
        if (cancelled) return;
        const flat = all
          .flat()
          .sort((a, b) => {
            if (a.date !== b.date) return a.date < b.date ? 1 : -1;
            return b.classification.confidence - a.classification.confidence;
          });
        setEntries(flat);
      } catch {
        if (!cancelled) setEntries([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: entries.length };
    for (const e of entries) {
      c[e.classification.label] = (c[e.classification.label] ?? 0) + 1;
    }
    return c;
  }, [entries]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((e) => {
      if (filter !== "all" && e.classification.label !== filter) return false;
      if (!q) return true;
      const hay = `${e.paper.title} ${e.paper.authors.join(" ")} ${
        e.paper.journal ?? ""
      }`.toLowerCase();
      return hay.includes(q);
    });
  }, [entries, filter, query]);

  return (
    <div className="flex h-screen flex-col">
      <TopNav active="flagged" />

      <main className="lc-scroll flex-1 overflow-y-auto bg-bg">
        <div className="mx-auto box-border max-w-[1080px] px-14 pb-20 pt-14">
          {/* Header */}
          <h1 className="mb-1 font-sans text-[34px] font-semibold tracking-[-0.01em] text-primary-text">
            Flagged Papers
          </h1>
          <p className="mb-8 font-sans text-[15px] leading-[1.6] text-muted-text">
            Every paper Baskr has surfaced for your lab, across all digests.
          </p>

          {/* Controls — label filters + search */}
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap gap-2">
              {FILTERS.map((f) => {
                const active = filter === f.key;
                const accent =
                  f.key === "all" ? "" : LABEL_STYLES[f.key].labelClass;
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => setFilter(f.key)}
                    className={`flex items-center gap-2 rounded-full border px-[14px] py-[6px] font-sans text-[13px] transition-colors duration-150 ${
                      active
                        ? "border-field-border bg-surface-hover text-primary-text"
                        : "border-divider bg-transparent text-muted-text hover:border-field-border hover:text-secondary-text"
                    }`}
                  >
                    {f.key !== "all" && (
                      <span
                        className={`h-2 w-2 rounded-full ${LABEL_STYLES[f.key].dotClass}`}
                      />
                    )}
                    <span className={active ? accent : ""}>{f.label}</span>
                    <span className="text-faint-text">
                      {counts[f.key] ?? 0}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="ml-auto flex items-center gap-2 rounded-[10px] border border-field-border bg-surface px-3 py-2">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="flex-shrink-0 text-faint-text"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search titles, authors…"
                className="w-[200px] bg-transparent font-sans text-[13.5px] text-primary-text outline-none placeholder:text-[#6b6f76]"
              />
            </div>
          </div>

          {/* Table */}
          <div className="overflow-hidden rounded-[12px] border border-divider">
            {/* Header row */}
            <div className="grid grid-cols-[minmax(0,1fr)_180px_140px_90px_110px] gap-4 border-b border-divider bg-surface px-5 py-[11px] font-sans text-[11px] font-semibold uppercase tracking-[0.07em] text-faint-text">
              <div>Paper</div>
              <div>Authors</div>
              <div>Classification</div>
              <div className="text-right">Match</div>
              <div className="text-right">Date</div>
            </div>

            {loading ? (
              <div className="px-5 py-10 text-center font-sans text-[14px] text-muted-text">
                Loading papers…
              </div>
            ) : visible.length === 0 ? (
              <div className="px-5 py-10 text-center font-sans text-[14px] text-muted-text">
                No papers match this view.
              </div>
            ) : (
              visible.map((entry, i) => {
                const style = LABEL_STYLES[entry.classification.label];
                return (
                  <button
                    type="button"
                    key={`${entry.paper.uid ?? entry.paper.source_id}-${i}`}
                    onClick={(e) =>
                      setSelected({
                        entry,
                        rect: e.currentTarget.getBoundingClientRect(),
                      })
                    }
                    className="grid w-full grid-cols-[minmax(0,1fr)_180px_140px_90px_110px] items-center gap-4 border-b border-divider px-5 py-[14px] text-left transition-colors duration-150 last:border-b-0 hover:bg-surface-hover"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        className={`h-2 w-2 flex-shrink-0 rounded-full ${style.dotClass}`}
                      />
                      <span className="truncate font-sans text-[14px] font-medium text-primary-text">
                        {entry.paper.title}
                      </span>
                    </div>
                    <div className="truncate font-sans text-[13px] text-muted-text">
                      {authorLabel(entry)}
                    </div>
                    <div
                      className={`truncate font-sans text-[12.5px] ${style.labelClass}`}
                    >
                      {style.category}
                    </div>
                    <div className="text-right font-sans text-[13px] tabular-nums text-secondary-text">
                      {entry.classification.confidence > 0
                        ? `${Math.round(entry.classification.confidence * 100)}%`
                        : "—"}
                    </div>
                    <div className="text-right font-sans text-[12.5px] tabular-nums text-faint-text">
                      {entry.date}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </main>

      {selected && (
        <PaperExpandModal
          entry={selected.entry}
          originRect={selected.rect}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
