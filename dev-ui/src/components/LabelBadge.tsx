import type { Label } from "../types";

const LABEL_STYLES: Record<Label, string> = {
  ANSWERS: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  CONTRADICTS: "bg-red-500/20 text-red-300 border-red-500/30",
  EXTENDS: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  NOT_RELEVANT: "bg-slate-500/20 text-slate-400 border-slate-500/30",
  SCOOP: "bg-amber-500/20 text-amber-300 border-amber-500/30",
};

export function LabelBadge({ label }: { label: Label }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${LABEL_STYLES[label]}`}
    >
      {label}
    </span>
  );
}
