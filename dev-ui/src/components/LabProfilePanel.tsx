import { useEffect, useState } from "react";
import { fetchProfile } from "../api";
import type { Profile, ProfileItem, ProfileItemKind } from "../types";

const KIND_LABEL: Record<ProfileItemKind, string> = {
  open_question: "Open Question",
  assumption: "Assumption",
  finding: "Finding",
  planned_experiment: "Planned Experiment",
};

const KIND_COLOR: Record<ProfileItemKind, string> = {
  open_question: "text-cyan-400",
  assumption: "text-amber-400",
  finding: "text-emerald-400",
  planned_experiment: "text-purple-400",
};

function ProfileItemRow({ item }: { item: ProfileItem }) {
  return (
    <div className="flex gap-3 py-2.5 border-b border-slate-800 last:border-0">
      <span
        className={`mt-0.5 text-[10px] font-semibold uppercase tracking-widest w-28 flex-shrink-0 ${KIND_COLOR[item.kind]}`}
      >
        {KIND_LABEL[item.kind]}
      </span>
      <p className="text-sm text-slate-300 leading-relaxed">{item.text}</p>
    </div>
  );
}

export function LabProfilePanel() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchProfile()
      .then((p) => {
        setProfile(p);
        setError(p === null);
      })
      .finally(() => setLoading(false));
  }, []);

  const kindOrder: ProfileItemKind[] = [
    "open_question",
    "assumption",
    "finding",
    "planned_experiment",
  ];
  const grouped = kindOrder.map((kind) => ({
    kind,
    items: profile?.items.filter((i) => i.kind === kind) ?? [],
  }));

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Lab Profile
        {profile && (
          <span className="ml-2 text-xs font-normal normal-case text-slate-600">
            {profile.display_name} · {profile.items.length} items
          </span>
        )}
      </h2>

      {loading && <p className="text-xs text-slate-500">Loading profile…</p>}
      {error && (
        <p className="text-xs text-red-400">
          Could not load profile from <code>/api/profile</code>.
        </p>
      )}
      {profile && profile.items.length === 0 && (
        <p className="text-xs text-slate-500">
          Profile is empty. Run <code>python -m app.seed_profile</code> to seed it.
        </p>
      )}
      {profile && (
        <div>
          {grouped.map(
            ({ kind, items }) =>
              items.length > 0 && (
                <div key={kind}>
                  {items.map((item) => (
                    <ProfileItemRow key={item.id} item={item} />
                  ))}
                </div>
              ),
          )}
        </div>
      )}
    </section>
  );
}
