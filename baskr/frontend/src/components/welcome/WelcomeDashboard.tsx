// Welcome / home screen (handoff "Main Welcome Screen").
// Greets the user, then surfaces newly-relevant papers grouped by the
// relationship they have to the lab's work, one accent colour per column.
import { useEffect, useState } from "react";
import { getDigest, getDigestHistory } from "../../api";
import type { DigestEntry, Label } from "../../types";
import TopNav from "./TopNav";
import PaperThumbnail from "./PaperThumbnail";

// Accent + label copy per classification label. Tailwind can't build class
// names dynamically, so each is a literal string it can see at build time.
const LABEL_STYLES: Record<
  Label,
  { category: string; borderClass: string; labelClass: string; linkClass: string }
> = {
  CONTRADICTS: {
    category: "Contradiction published",
    borderClass: "border-coral",
    labelClass: "text-coral",
    linkClass: "text-coral",
  },
  EXTENDS: {
    category: "Knowledge gap filled",
    borderClass: "border-amber",
    labelClass: "text-amber",
    linkClass: "text-amber",
  },
  ANSWERS: {
    category: "Answer to open question",
    borderClass: "border-teal",
    labelClass: "text-teal",
    linkClass: "text-teal",
  },
  SCOOP: {
    category: "Potential scoop",
    borderClass: "border-violet",
    labelClass: "text-violet",
    linkClass: "text-violet",
  },
  NOT_RELEVANT: {
    category: "Related work",
    borderClass: "border-navy",
    labelClass: "text-navy",
    linkClass: "text-navy",
  },
};

const USER_NAME = "Toby"; // TODO: from auth/user profile
const MAX_CARDS = 4;

// Short author/source label shown as the in-text link.
function sourceLabel(entry: DigestEntry): string {
  const { authors, journal, source } = entry.paper;
  if (authors.length > 0) {
    return authors.length > 1 ? `${authors[0]} et al.` : authors[0];
  }
  return journal || source;
}

export default function WelcomeDashboard() {
  const [cards, setCards] = useState<DigestEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const history = await getDigestHistory();
        if (history.length === 0) {
          if (!cancelled) setCards([]);
          return;
        }
        // history is newest-first; take the latest digest's top hits.
        const entries = await getDigest(history[0].date);
        const top = [...entries]
          .sort((a, b) => b.classification.confidence - a.classification.confidence)
          .slice(0, MAX_CARDS);
        if (!cancelled) setCards(top);
      } catch {
        if (!cancelled) setCards([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-screen flex-col">
      <TopNav active="dashboard" />

      <main className="flex flex-1 flex-col items-center overflow-y-auto bg-page-bg px-[72px] pb-[72px] pt-16">
        {/* Greeting */}
        <div className="mb-12 w-full text-center">
          <h1 className="font-serif text-[42px] font-normal leading-[1.3] text-navy">
            Welcome back {USER_NAME}!
          </h1>
          <p className="font-serif text-[42px] font-normal leading-[1.3] text-navy">
            The world's been busy:
          </p>
        </div>

        {loading ? (
          <p className="font-serif text-[16px] text-navy/60">Loading the latest…</p>
        ) : cards.length === 0 ? (
          <p className="font-serif text-[16px] text-navy/60">
            No recent papers to show yet.
          </p>
        ) : (
          /* Paper cards — three aligned rows (thumbnails, labels, descriptions).
             Rendered as three passes so each row lines up across all columns. */
          <div className="grid w-full max-w-[860px] grid-cols-4 gap-x-7 gap-y-[13px]">
            {cards.map((entry) => {
              const style = LABEL_STYLES[entry.classification.label];
              return (
                <div
                  key={`thumb-${entry.paper.uid}`}
                  className={`h-[200px] overflow-hidden border-[3px] bg-white ${style.borderClass}`}
                >
                  <PaperThumbnail paper={entry.paper} />
                </div>
              );
            })}

            {cards.map((entry) => {
              const style = LABEL_STYLES[entry.classification.label];
              return (
                <div
                  key={`label-${entry.paper.uid}`}
                  className={`text-center font-serif text-[13px] font-bold leading-[1.3] ${style.labelClass}`}
                >
                  {style.category}
                </div>
              );
            })}

            {cards.map((entry) => {
              const style = LABEL_STYLES[entry.classification.label];
              return (
                <p
                  key={`desc-${entry.paper.uid}`}
                  className="text-center font-serif text-[12px] leading-[1.65] text-navy"
                >
                  <a
                    href={entry.paper.url ?? "#"}
                    target="_blank"
                    rel="noreferrer"
                    className={`underline ${style.linkClass}`}
                  >
                    {sourceLabel(entry)}
                  </a>
                  {` — ${entry.classification.reason}`}
                </p>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
