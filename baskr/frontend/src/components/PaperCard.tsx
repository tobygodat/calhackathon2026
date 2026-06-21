// Title, citation, LabelBadge, one-sentence reason, PubMed link (SPEC §9).
import type { Classification, Paper } from "../types";
import LabelBadge from "./LabelBadge";

interface PaperCardProps {
  paper: Paper;
  classification: Classification;
}

export default function PaperCard(_props: PaperCardProps) {
  // TODO: render title, citation, <LabelBadge>, reason, and source link.
  return (
    <article className="rounded-md border border-neutral-800 p-3">
      <LabelBadge label="NOT_RELEVANT" />
      <p className="text-sm text-neutral-500">TODO: paper card.</p>
    </article>
  );
}
