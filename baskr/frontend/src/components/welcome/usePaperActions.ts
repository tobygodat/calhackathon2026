// Save / dismiss state for paper cards.
//
// Interim persistence is localStorage so the actions work end-to-end today.
// When the backend grows the endpoints below, swap the localStorage writes for
// real calls — the component API here won't change:
//   • save    → POST /api/papers/save     (a per-lab reading list)
//   • dismiss → POST /api/papers/dismiss  (a "not relevant" signal that the
//               classifier folds back into the lab profile)
import { useCallback, useState } from "react";
import type { DigestEntry } from "../../types";

const SAVED_KEY = "baskr:saved";
const DISMISSED_KEY = "baskr:dismissed";

// Stable identity for a paper (uid when present, else source + id).
export function paperKey(entry: DigestEntry): string {
  return entry.paper.uid ?? `${entry.paper.source}:${entry.paper.source_id}`;
}

function load(key: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
  } catch {
    return new Set();
  }
}

function persist(key: string, set: Set<string>) {
  try {
    localStorage.setItem(key, JSON.stringify([...set]));
  } catch {
    /* storage unavailable — actions still work for the session */
  }
}

export function usePaperActions() {
  const [saved, setSaved] = useState<Set<string>>(() => load(SAVED_KEY));
  const [dismissed, setDismissed] = useState<Set<string>>(() =>
    load(DISMISSED_KEY)
  );

  const toggleSave = useCallback((entry: DigestEntry) => {
    const k = paperKey(entry);
    setSaved((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      persist(SAVED_KEY, next);
      // TODO(backend): POST /api/papers/save { uid, saved: next.has(k) }.
      return next;
    });
  }, []);

  const dismiss = useCallback((entry: DigestEntry) => {
    const k = paperKey(entry);
    setDismissed((prev) => {
      const next = new Set(prev).add(k);
      persist(DISMISSED_KEY, next);
      // TODO(backend): POST /api/papers/dismiss { uid } so the profile learns.
      return next;
    });
  }, []);

  const restore = useCallback((entry: DigestEntry) => {
    const k = paperKey(entry);
    setDismissed((prev) => {
      const next = new Set(prev);
      next.delete(k);
      persist(DISMISSED_KEY, next);
      return next;
    });
  }, []);

  return { saved, dismissed, toggleSave, dismiss, restore };
}
