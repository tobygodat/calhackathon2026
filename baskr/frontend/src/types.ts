// Mirrors backend/app/models.py (SPEC §5). Keep in sync.

export type ProfileItemKind =
  | "open_question"
  | "assumption"
  | "finding"
  | "planned_experiment";

export type Label =
  | "ANSWERS"
  | "CONTRADICTS"
  | "EXTENDS"
  | "NOT_RELEVANT"
  | "SCOOP";

export interface ProfileItem {
  id: string;
  kind: ProfileItemKind;
  text: string;
}

export interface Profile {
  lab_id: string;
  niche: string;
  display_name: string;
  items: ProfileItem[];
}

// Mirrors PaperOut (data_pipeline Paper.to_dict()).
export interface Paper {
  source: string;
  source_id: string;
  title: string;
  abstract: string;
  authors: string[];
  doi: string | null;
  url: string | null;
  journal: string | null;
  published: string | null;
  categories: string[];
  uid: string | null;
}

export interface Classification {
  label: Label;
  reason: string;
  matched_item_id: string | null;
  confidence: number;
}

export interface SearchHit {
  paper: Paper;
  classification: Classification;
}

export interface DigestSummary {
  date: string;
  count: number;
  top_label: Label;
}

export interface DigestEntry {
  date: string;
  paper: Paper;
  classification: Classification;
}
