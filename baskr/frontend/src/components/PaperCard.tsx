import type { Classification, Paper } from "../types";
import LabelBadge from "./LabelBadge";

interface PaperCardProps {
  paper: Paper;
  classification: Classification;
}

export default function PaperCard({ paper, classification }: PaperCardProps) {
  const firstAuthor = paper.authors[0] ?? "Unknown";
  const etAl = paper.authors.length > 1 ? " et al." : "";
  const year = (paper.published ?? "").slice(0, 4);
  const venue = paper.journal ?? paper.source;
  const citation = `${firstAuthor}${etAl}${year ? ` (${year})` : ""}. ${venue}.`;

  return (
    <article className="rounded-md border border-neutral-800 bg-neutral-900/40 p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <LabelBadge label={classification.label} />
        {classification.confidence > 0 && (
          <span className="text-xs text-neutral-500 shrink-0">
            {Math.round(classification.confidence * 100)}% conf.
          </span>
        )}
      </div>

      <div>
        {paper.url ? (
          <a
            href={paper.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium leading-snug text-neutral-100 hover:text-cyan-400 hover:underline"
          >
            {paper.title}
          </a>
        ) : (
          <p className="text-sm font-medium leading-snug text-neutral-100">{paper.title}</p>
        )}
        <p className="mt-0.5 text-xs text-neutral-500">{citation}</p>
      </div>

      {classification.reason && (
        <p className="text-sm leading-relaxed text-neutral-300 border-l-2 border-neutral-700 pl-2">
          {classification.reason}
        </p>
      )}
    </article>
  );
}
