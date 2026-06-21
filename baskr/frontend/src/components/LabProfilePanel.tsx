import { useEffect, useState } from "react";
import { getProfile } from "../api";
import type { Profile, ProfileItem, ProfileItemKind } from "../types";

const KIND_LABELS: Record<ProfileItemKind, string> = {
  open_question: "Open Question",
  assumption: "Assumption",
  finding: "Finding",
  planned_experiment: "Planned Experiment",
};

const KIND_STYLES: Record<ProfileItemKind, string> = {
  open_question: "border-l-2 border-violet-500 pl-3",
  assumption: "border-l-2 border-amber-500 pl-3",
  finding: "border-l-2 border-emerald-500 pl-3",
  planned_experiment: "border-l-2 border-cyan-500 pl-3",
};

const KIND_BADGE: Record<ProfileItemKind, string> = {
  open_question: "bg-violet-900/50 text-violet-300",
  assumption: "bg-amber-900/50 text-amber-300",
  finding: "bg-emerald-900/50 text-emerald-300",
  planned_experiment: "bg-cyan-900/50 text-cyan-300",
};

function groupByKind(items: ProfileItem[]): Record<ProfileItemKind, ProfileItem[]> {
  const groups: Record<string, ProfileItem[]> = {};
  for (const item of items) {
    if (!groups[item.kind]) groups[item.kind] = [];
    groups[item.kind].push(item);
  }
  return groups as Record<ProfileItemKind, ProfileItem[]>;
}

const KIND_ORDER: ProfileItemKind[] = [
  "open_question",
  "assumption",
  "finding",
  "planned_experiment",
];

export default function LabProfilePanel() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 font-medium">Lab Profile</h2>
        <p className="text-xs text-red-400">Error: {error}</p>
      </section>
    );
  }

  if (!profile) {
    return (
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="mb-2 font-medium">Lab Profile</h2>
        <p className="text-sm text-neutral-500 animate-pulse">Loading…</p>
      </section>
    );
  }

  const groups = groupByKind(profile.items);

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-4">
        <h2 className="font-medium">{profile.display_name}</h2>
        <p className="text-xs text-neutral-500 mt-0.5">{profile.niche.replace(/_/g, " ")}</p>
      </div>

      <div className="space-y-4">
        {KIND_ORDER.map((kind) => {
          const items = groups[kind];
          if (!items?.length) return null;
          return (
            <div key={kind}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
                {KIND_LABELS[kind]}s
              </h3>
              <div className="space-y-2">
                {items.map((item) => (
                  <div key={item.id} className={`${KIND_STYLES[kind]} py-1`}>
                    <span
                      className={`mb-1 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${KIND_BADGE[kind]}`}
                    >
                      {item.id}
                    </span>
                    <p className="text-sm leading-snug text-neutral-200">{item.text}</p>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
