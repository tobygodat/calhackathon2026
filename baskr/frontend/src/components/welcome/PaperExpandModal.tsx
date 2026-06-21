// Click-to-expand paper detail overlay — "annotated figure" layout.
// The clicked card's rendered first page flies to a centred portrait frame;
// labelled blurbs fade in on either side, connected to the page with thin
// leader lines. Reused by the dashboard cards and the Flagged Papers rows.
import { useCallback, useEffect, useState } from "react";
import type { DigestEntry } from "../../types";
import { LABEL_STYLES } from "../../labelStyles";
import PaperThumbnail from "./PaperThumbnail";

interface PaperExpandModalProps {
  entry: DigestEntry;
  originRect: DOMRect; // start frame of the flying page
  onClose: () => void;
}

interface Layout {
  pageTop: number;
  pageLeft: number;
  pageW: number;
  pageH: number;
  sideW: number;
  gap: number;
  midY: number;
  leftLeft: number;
  rightLeft: number;
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

// Centred page + two flanking annotation columns, sized to the viewport.
function computeLayout(): Layout {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const pageH = Math.min(Math.round(vh * 0.62), 440);
  const pageW = Math.min(Math.round(pageH * 0.74), Math.round(vw * 0.26));
  const gap = 40;
  const sideW = clamp((vw - pageW) / 2 - gap - 24, 150, 240);
  const pageLeft = Math.round((vw - pageW) / 2);
  const pageTop = Math.round((vh - pageH) / 2);
  return {
    pageTop,
    pageLeft,
    pageW,
    pageH,
    sideW,
    gap,
    midY: pageTop + pageH / 2,
    leftLeft: pageLeft - gap - sideW,
    rightLeft: pageLeft + pageW + gap,
  };
}

function meta(entry: DigestEntry): string {
  const { authors, journal, source, published } = entry.paper;
  const who =
    authors.length === 0
      ? journal ?? source
      : authors.length > 2
        ? `${authors[0]} et al.`
        : authors.join(", ");
  const year = (published ?? "").slice(0, 4);
  return [who, journal ?? source, year].filter(Boolean).join("  ·  ");
}

const KEY = "font-sans text-[10px] font-semibold uppercase tracking-[0.1em] text-muted-text";

export default function PaperExpandModal({
  entry,
  originRect,
  onClose,
}: PaperExpandModalProps) {
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [L] = useState<Layout>(computeLayout);

  const handleClose = useCallback(() => setClosing(true), []);

  useEffect(() => {
    const id = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [handleClose]);

  const style = LABEL_STYLES[entry.classification.label];
  const expanded = open && !closing;
  const { paper, classification } = entry;
  const ease = "cubic-bezier(0.32, 0.72, 0, 1)";

  const pageBox: React.CSSProperties = expanded
    ? { top: L.pageTop, left: L.pageLeft, width: L.pageW, height: L.pageH }
    : {
        top: originRect.top,
        left: originRect.left,
        width: originRect.width,
        height: originRect.height,
      };

  // A labelled annotation block with a leader line drawing toward the page.
  const lead = (side: "left" | "right") => (
    <span
      aria-hidden
      style={{
        transformOrigin: side === "left" ? "right" : "left",
        transitionDelay: expanded ? "220ms" : "0ms",
      }}
      className={`absolute top-[7px] h-px w-[30px] bg-muted-border transition-transform duration-300 ${
        side === "left" ? "-right-[30px]" : "-left-[30px]"
      } ${expanded ? "scale-x-100" : "scale-x-0"}`}
    />
  );

  const annoClass = `fixed flex -translate-y-1/2 flex-col gap-7 overflow-hidden transition-opacity duration-300 ${
    expanded ? "opacity-100 delay-[120ms]" : "pointer-events-none opacity-0"
  }`;
  // Cap the columns to the viewport so a long abstract / reason can't spill past
  // the top and bottom edges (they're vertically centred on the page).
  const colMaxH = Math.round(window.innerHeight * 0.86);

  return (
    <div
      className={`fixed inset-0 z-50 bg-black/85 backdrop-blur-[3px] transition-opacity duration-300 ${
        expanded ? "opacity-100" : "opacity-0"
      }`}
      onClick={handleClose}
      role="presentation"
    >
      {/* Flying page — the artifact in the centre. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={paper.title}
        onClick={(e) => e.stopPropagation()}
        onTransitionEnd={(e) => {
          if (e.propertyName === "width" && closing) onClose();
        }}
        style={{ ...pageBox, transitionTimingFunction: ease }}
        className="fixed overflow-hidden rounded-[5px] bg-[#e9e9ea] shadow-[0_24px_60px_rgba(0,0,0,0.6)] transition-[top,left,width,height] duration-[400ms]"
      >
        <span className={`absolute inset-y-0 left-0 z-10 w-[3px] ${style.dotClass}`} />
        <PaperThumbnail paper={paper} />
      </div>

      {/* Left column — the classification (why Baskr surfaced it). */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ top: L.midY, left: L.leftLeft, width: L.sideW, maxHeight: colMaxH }}
        className={`${annoClass} items-end text-right`}
      >
        <div className="relative">
          {lead("left")}
          <div className={`${KEY} mb-1`}>Classification</div>
          <div className={`font-sans text-[13px] font-semibold ${style.labelClass}`}>
            {style.category}
          </div>
          {classification.confidence > 0 && (
            <div className="font-sans text-[12px] text-faint-text">
              {Math.round(classification.confidence * 100)}% match
            </div>
          )}
        </div>
        {classification.reason && (
          <div className="relative">
            {lead("left")}
            <div className={`${KEY} mb-1`}>Why it surfaced</div>
            <p className="line-clamp-[7] font-sans text-[13px] leading-[1.6] text-secondary-text [text-wrap:pretty]">
              {classification.reason}
            </p>
          </div>
        )}
      </div>

      {/* Right column — the paper itself (what it is). */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ top: L.midY, left: L.rightLeft, width: L.sideW, maxHeight: colMaxH }}
        className={`${annoClass} items-start text-left`}
      >
        <div className="relative">
          {lead("right")}
          <div className={`${KEY} mb-1`}>Paper</div>
          <h2 className="font-sans text-[18px] font-semibold leading-[1.28] tracking-[-0.015em] text-primary-text [text-wrap:pretty]">
            {paper.title}
          </h2>
          <div className="mt-1.5 font-sans text-[12px] text-muted-text">{meta(entry)}</div>
        </div>
        <div className="relative">
          {paper.abstract && (
            <>
              <div className={`${KEY} mb-1`}>Abstract</div>
              <p className="line-clamp-[8] font-sans text-[12px] leading-[1.65] text-secondary-text">
                {paper.abstract}
              </p>
            </>
          )}
          {paper.url && (
            <a
              href={paper.url}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 rounded-[8px] bg-primary-text px-[17px] py-[9px] font-sans text-[13px] font-medium text-bg transition-colors hover:bg-white"
            >
              Read paper
              <span aria-hidden>→</span>
            </a>
          )}
        </div>
      </div>

      {/* Close — quiet glyph, top-right of the overlay. */}
      <button
        type="button"
        onClick={handleClose}
        aria-label="Close"
        className={`fixed right-5 top-4 z-20 text-[22px] leading-none text-faint-text transition-all duration-200 hover:text-primary-text ${
          expanded ? "opacity-100 delay-[150ms]" : "opacity-0"
        }`}
      >
        ×
      </button>
    </div>
  );
}
