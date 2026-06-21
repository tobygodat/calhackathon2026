// Shared paper card grid — the three aligned rows (thumbnails, labels,
// descriptions) plus the click-to-expand modal. Used by the welcome dashboard
// and the search results page so both render hits identically.
import { useEffect, useRef, useState } from "react";
import type { DigestEntry } from "../../types";
import { LABEL_STYLES } from "../../labelStyles";
import PaperThumbnail from "./PaperThumbnail";
import PaperExpandModal from "./PaperExpandModal";
import { usePaperActions, paperKey } from "./usePaperActions";

// Short author/source label shown as the in-text link.
function sourceLabel(entry: DigestEntry): string {
  const { authors, journal, source } = entry.paper;
  if (authors.length > 0) {
    return authors.length > 1 ? `${authors[0]} et al.` : authors[0];
  }
  return journal || source;
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" />
    </svg>
  );
}

function CrossIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="6" y1="6" x2="18" y2="18" />
      <line x1="18" y1="6" x2="6" y2="18" />
    </svg>
  );
}

const ACT =
  "flex h-7 w-7 items-center justify-center rounded-[8px] bg-bg/80 backdrop-blur transition-colors duration-150";

export default function PaperCardGrid({ entries }: { entries: DigestEntry[] }) {
  // The card the user clicked, plus its on-screen rect — drives the expand
  // animation in PaperExpandModal.
  const [selected, setSelected] = useState<{
    entry: DigestEntry;
    rect: DOMRect;
  } | null>(null);

  const { saved, dismissed, toggleSave, dismiss, restore } = usePaperActions();
  // Key mid-exit (plays the collapse before it's removed) + the last dismissed
  // entry for the undo toast.
  const [leaving, setLeaving] = useState<string | null>(null);
  const [undoEntry, setUndoEntry] = useState<DigestEntry | null>(null);
  const undoTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(undoTimer.current), []);

  const visible = entries.filter((e) => !dismissed.has(paperKey(e)));

  const handleDismiss = (entry: DigestEntry) => {
    const k = paperKey(entry);
    setLeaving(k); // play the collapse, then actually remove
    window.setTimeout(() => {
      dismiss(entry);
      setLeaving(null);
      setUndoEntry(entry);
      window.clearTimeout(undoTimer.current);
      undoTimer.current = window.setTimeout(() => setUndoEntry(null), 6000);
    }, 220);
  };

  const handleUndo = () => {
    if (undoEntry) restore(undoEntry);
    setUndoEntry(null);
  };

  // Page-load choreography (see index.css): greeting first (delay 0, owned by
  // the page), then covers deal in one by one, then the caption rows.
  const COVER_BASE = 120; // ms after mount before the first cover deals
  const COVER_STAGGER = 90; // ms between covers
  const captionDelay = COVER_BASE + visible.length * COVER_STAGGER;

  return (
    <>
      {/* Paper cards — three aligned rows (thumbnails, labels, descriptions).
         Rendered as three passes, so each pass must fill exactly one row:
         the column count has to match the number of cards (handoff shows 4,
         but a digest can have fewer). Fixed 194px columns keep card size
         constant and centre the grid regardless of count. */}
      <div
        className="grid gap-x-7 gap-y-[14px]"
        style={{ gridTemplateColumns: `repeat(${visible.length}, 194px)` }}
      >
        {visible.map((entry, i) => {
          const style = LABEL_STYLES[entry.classification.label];
          const k = paperKey(entry);
          const isSaved = saved.has(k);
          const isLeaving = leaving === k;
          return (
            // Cover stack: the rendered first page sits on top of two faint
            // pages peeking behind, so it reads as a physical document.
            <div
              key={`thumb-${k}`}
              className="baskr-deal relative h-[200px] w-[194px]"
              style={{ animationDelay: `${COVER_BASE + i * COVER_STAGGER}ms` }}
            >
              {/* Inner wrapper owns the exit transition (kept off the element
                  that runs the entrance animation, whose fill would lock it). */}
              <div
                className={`relative h-full w-full transition-all duration-200 ease-in ${
                  isLeaving ? "scale-90 opacity-0" : "opacity-100"
                }`}
              >
                <div
                  aria-hidden
                  className="absolute inset-0 translate-x-[6px] translate-y-[6px] rotate-[1.4deg] rounded-[4px] bg-[#d9dadd] shadow-[0_8px_22px_rgba(0,0,0,0.45)]"
                />
                <div
                  aria-hidden
                  className="absolute inset-0 translate-x-[3px] translate-y-[3px] -rotate-[0.6deg] rounded-[4px] bg-[#e4e6e9]"
                />
                {/* Cover is a div (not a button) so the action buttons can nest
                    inside it legally and lift with it on hover. */}
                <div
                  role="button"
                  tabIndex={0}
                  aria-label={`Open ${entry.paper.title}`}
                  onClick={(e) =>
                    setSelected({
                      entry,
                      rect: e.currentTarget.getBoundingClientRect(),
                    })
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelected({
                        entry,
                        rect: e.currentTarget.getBoundingClientRect(),
                      });
                    }
                  }}
                  className={`group absolute inset-0 cursor-pointer overflow-hidden rounded-[4px] border-t-[3px] bg-[#e9e9ea] shadow-[0_14px_30px_rgba(0,0,0,0.5)] outline-none transition-transform duration-200 ease-out hover:-translate-y-1 focus-visible:-translate-y-1 ${style.borderClass}`}
                >
                  <span
                    className={`absolute left-2 top-2 z-10 rounded-[4px] px-[7px] py-[3px] text-[10px] font-bold tracking-[0.04em] text-white ${style.dotClass}`}
                  >
                    {entry.classification.label}
                  </span>

                  {/* Save + dismiss — revealed on hover, or kept up if saved. */}
                  <div
                    className={`absolute right-2 top-2 z-20 flex gap-1.5 transition-opacity duration-150 ${
                      isSaved ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                    }`}
                  >
                    <button
                      type="button"
                      aria-label={isSaved ? "Saved — click to unsave" : "Save"}
                      title={isSaved ? "Saved" : "Save"}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSave(entry);
                      }}
                      className={`${ACT} ${
                        isSaved
                          ? "text-primary-text"
                          : "text-secondary-text hover:text-primary-text"
                      }`}
                    >
                      <BookmarkIcon filled={isSaved} />
                    </button>
                    <button
                      type="button"
                      aria-label="Not relevant"
                      title="Not relevant"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDismiss(entry);
                      }}
                      className={`${ACT} text-secondary-text hover:text-primary-text`}
                    >
                      <CrossIcon />
                    </button>
                  </div>

                  <div className="h-full w-full transition-transform duration-300 ease-out group-hover:scale-[1.04]">
                    <PaperThumbnail paper={entry.paper} />
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {visible.map((entry) => {
          const style = LABEL_STYLES[entry.classification.label];
          return (
            <div
              key={`label-${paperKey(entry)}`}
              className="baskr-rise text-center"
              style={{ animationDelay: `${captionDelay}ms` }}
            >
              <span
                className={`inline-block rounded-[5px] px-2.5 py-1 font-sans text-[13px] font-semibold leading-[1.35] text-white ${style.dotClass}`}
              >
                {style.category}
              </span>
            </div>
          );
        })}

        {visible.map((entry) => {
          const style = LABEL_STYLES[entry.classification.label];
          return (
            <p
              key={`desc-${paperKey(entry)}`}
              className="baskr-rise line-clamp-4 text-center font-sans text-[12.5px] leading-[1.6] text-secondary-text [text-wrap:pretty]"
              style={{ animationDelay: `${captionDelay + 80}ms` }}
            >
              <a
                href={entry.paper.url ?? "#"}
                target="_blank"
                rel="noreferrer"
                className={`underline ${style.linkClass}`}
              >
                {sourceLabel(entry)}
              </a>
              {` — ${entry.classification.reason}`}
            </p>
          );
        })}
      </div>

      {/* Undo toast after a dismiss. */}
      {undoEntry && (
        <div className="fixed bottom-7 left-1/2 z-40 flex -translate-x-1/2 items-center gap-4 rounded-[10px] border border-field-border bg-surface px-4 py-2.5 font-sans text-[13px] text-muted-text shadow-[0_16px_40px_rgba(0,0,0,0.5)]">
          <span>
            <span className="text-primary-text">Marked not relevant.</span> We'll
            show fewer like it.
          </span>
          <button
            type="button"
            onClick={handleUndo}
            className="font-medium text-primary-text underline underline-offset-2 hover:no-underline"
          >
            Undo
          </button>
        </div>
      )}

      {selected && (
        <PaperExpandModal
          entry={selected.entry}
          originRect={selected.rect}
          onClose={() => setSelected(null)}
        />
      )}
    </>
  );
}
