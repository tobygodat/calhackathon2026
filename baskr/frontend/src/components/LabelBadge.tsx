// Colored chip per label (SPEC §9):
// CONTRADICTS=red, ANSWERS=green, EXTENDS=blue, NOT_RELEVANT=gray.
import type { Label } from "../types";

const LABEL_STYLES: Record<Label, string> = {
  CONTRADICTS: "bg-red-900 text-red-200",
  ANSWERS: "bg-green-900 text-green-200",
  EXTENDS: "bg-blue-900 text-blue-200",
  NOT_RELEVANT: "bg-neutral-800 text-neutral-400",
  SCOOP: "bg-purple-900 text-purple-200", // stretch
};

interface LabelBadgeProps {
  label: Label;
}

export default function LabelBadge({ label }: LabelBadgeProps) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${LABEL_STYLES[label]}`}>
      {label}
    </span>
  );
}
