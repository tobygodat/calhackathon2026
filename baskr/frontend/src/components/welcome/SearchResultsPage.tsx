// Active-query search results (#/search?q=…). Takes the research question from
// the URL, runs it through the live active-search backend, and renders the
// classified hits with the same card grid + expand modal as the dashboard.
import { useEffect, useState } from "react";
import { search } from "../../api";
import type { DigestEntry, SearchHit } from "../../types";
import TopNav from "./TopNav";
import PaperCardGrid from "./PaperCardGrid";

// A SearchHit is a DigestEntry minus `date`; add an empty one so the card grid
// and expand modal (which expect DigestEntry) accept it unchanged.
function toEntry(hit: SearchHit): DigestEntry {
  return { ...hit, date: "" };
}

export default function SearchResultsPage({ query }: { query: string }) {
  const [hits, setHits] = useState<DigestEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setHits([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    (async () => {
      try {
        const results = await search(q);
        if (!cancelled) setHits(results.map(toEntry));
      } catch {
        if (!cancelled) setError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <div className="flex h-screen flex-col">
      <TopNav active="search" />

      <main className="flex flex-1 flex-col items-center overflow-y-auto bg-bg px-[72px] pb-[72px] pt-16">
        {/* Header — first beat of the page-load sequence (results follow). */}
        <div className="baskr-rise mb-[52px] w-full text-center">
          <p className="mb-2 font-sans text-[15px] tracking-[0.01em] text-muted-text">
            Results for
          </p>
          <h1 className="font-sans text-[40px] font-semibold leading-[1.25] tracking-[-0.015em] text-primary-text [text-wrap:balance]">
            "{query}"
          </h1>
        </div>

        {loading ? (
          <p className="font-sans text-[16px] text-muted-text">
            Searching the literature…
          </p>
        ) : error ? (
          <p className="font-sans text-[16px] text-muted-text">
            Something went wrong. Try again.
          </p>
        ) : hits.length === 0 ? (
          <p className="font-sans text-[16px] text-muted-text">
            No relevant papers found.
          </p>
        ) : (
          <PaperCardGrid entries={hits} />
        )}
      </main>
    </div>
  );
}
