import type { Classification, Paper } from "../types";
import { LabelBadge } from "./LabelBadge";

interface PaperCardProps {
  paper: Paper;
  classification: Classification;
}

export function PaperCard({ paper, classification }: PaperCardProps) {
  const authorStr =
    paper.authors.length > 0
      ? paper.authors.length > 3
        ? `${paper.authors.slice(0, 3).join(", ")} et al.`
        : paper.authors.join(", ")
      : "Unknown authors";

  const pubmedUrl =
    paper.source === "pubmed" && paper.source_id
      ? `https://pubmed.ncbi.nlm.nih.gov/${paper.source_id}/`
      : paper.url ?? undefined;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {pubmedUrl ? (
            <a
              href={pubmedUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-slate-100 hover:text-cyan-300 transition-colors leading-tight"
            >
              {paper.title}
            </a>
          ) : (
            <p className="text-sm font-medium text-slate-100 leading-tight">{paper.title}</p>
          )}
        </div>
        <div className="flex-shrink-0">
          <LabelBadge label={classification.label} />
        </div>
      </div>

      <p className="text-xs text-slate-500">
        {authorStr}
        {paper.journal ? ` · ${paper.journal}` : ""}
        {paper.published ? ` · ${paper.published}` : ""}
        {" · "}
        <span className="uppercase tracking-wide">{paper.source}</span>
      </p>

      <p className="text-xs text-slate-300 leading-relaxed border-l-2 border-slate-600 pl-3">
        {classification.reason}
      </p>

      <div className="flex items-center gap-3 text-xs text-slate-600">
        <span>conf {(classification.confidence * 100).toFixed(0)}%</span>
        {classification.matched_item_id && (
          <span>→ {classification.matched_item_id}</span>
        )}
        {pubmedUrl && (
          <a
            href={pubmedUrl}
            target="_blank"
            rel="noreferrer"
            className="text-cyan-600 hover:text-cyan-400 transition-colors"
          >
            View source ↗
          </a>
        )}
      </div>
    </div>
  );
}
