// Accent + label copy per classification label, shared across the dashboard,
// the expand modal, and the Flagged Papers table. Tailwind can't build class
// names dynamically, so each is a literal string it can see at build time.
import type { Label } from "./types";

export interface LabelStyle {
  category: string; // human-readable category for the label
  borderClass: string; // accent border (cards, modal frame)
  labelClass: string; // accent text (category line, badge)
  linkClass: string; // accent text for links
  dotClass: string; // accent background (status dot, chips)
}

export const LABEL_STYLES: Record<Label, LabelStyle> = {
  CONTRADICTS: {
    category: "Contradiction published",
    borderClass: "border-coral",
    labelClass: "text-coral",
    linkClass: "text-coral",
    dotClass: "bg-coral",
  },
  EXTENDS: {
    category: "Knowledge gap filled",
    borderClass: "border-amber",
    labelClass: "text-amber",
    linkClass: "text-amber",
    dotClass: "bg-amber",
  },
  ANSWERS: {
    category: "Answer to open question",
    borderClass: "border-teal",
    labelClass: "text-teal",
    linkClass: "text-teal",
    dotClass: "bg-teal",
  },
  SCOOP: {
    category: "Potential scoop",
    borderClass: "border-violet",
    labelClass: "text-violet",
    linkClass: "text-violet",
    dotClass: "bg-violet",
  },
  NOT_RELEVANT: {
    category: "Related work",
    borderClass: "border-muted-border",
    labelClass: "text-secondary-text",
    linkClass: "text-secondary-text",
    dotClass: "bg-muted-border",
  },
};
