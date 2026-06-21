// Welcome / home screen (handoff "Main Welcome Screen").
// Greets the user, then surfaces newly-relevant papers grouped by the
// relationship they have to the lab's work, one accent colour per column.
import { useEffect, useState } from "react";
import { getDigest, getDigestHistory } from "../../api";
import type { DigestEntry } from "../../types";
import TopNav from "./TopNav";
import PaperCardGrid from "./PaperCardGrid";

const USER_NAME = "Toby"; // TODO: from auth/user profile
const MAX_CARDS = 4;

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

      <main className="flex flex-1 flex-col items-center overflow-y-auto bg-bg px-[72px] pb-[72px] pt-16">
        {/* Greeting — first beat of the page-load sequence (cards follow). */}
        <div className="baskr-rise mb-[52px] w-full text-center">
          <h1 className="font-sans text-[44px] font-semibold leading-[1.25] tracking-[-0.015em] text-primary-text">
            Welcome back {USER_NAME}!
          </h1>
          <p className="font-sans text-[44px] font-semibold leading-[1.25] tracking-[-0.015em] text-primary-text">
            The world's been busy:
          </p>
        </div>

        {loading ? (
          <p className="font-sans text-[16px] text-muted-text">Loading the latest…</p>
        ) : cards.length === 0 ? (
          <p className="font-sans text-[16px] text-muted-text">
            No recent papers to show yet.
          </p>
        ) : (
          <PaperCardGrid entries={cards} />
        )}
      </main>
    </div>
  );
}
