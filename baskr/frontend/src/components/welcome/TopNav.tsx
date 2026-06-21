// Fixed 56px top nav (handoff "Shared Top Nav Bar").
// Shared across the Research Dashboard and Lab Context pages.
// Left/right monochrome links and a centre search pill that expands on hover.
// The pill is a live search form: type a research question and Enter runs the
// active-query search (#/search?q=…). `active` highlights the current page.
import { useState } from "react";

const linkClass =
  "font-sans text-[14px] tracking-[0.01em] text-muted-text no-underline transition-colors duration-200 hover:text-primary-text";
const activeLinkClass =
  "font-sans text-[14px] tracking-[0.01em] text-primary-text no-underline transition-colors duration-200 hover:text-primary-text";

// Current ?q= so the search box stays filled while on the results route.
function currentQuery(): string {
  const hash = window.location.hash;
  if (!hash.startsWith("#/search")) return "";
  return new URLSearchParams(hash.split("?")[1] ?? "").get("q") ?? "";
}

interface TopNavProps {
  // Which page is rendering this nav, so its link shows the active colour.
  active?: "dashboard" | "labContext" | "flagged" | "search";
}

export default function TopNav({ active }: TopNavProps) {
  const [query, setQuery] = useState(currentQuery);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    window.location.hash = `#/search?q=${encodeURIComponent(q)}`;
  };

  return (
    <nav className="grid h-14 flex-shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-divider bg-bg px-6">
      <div className="flex items-center justify-self-start">
        {/* Wordmark doubles as the home link (replaces the old top-right house). */}
        <a
          href="#/"
          aria-label="Baskr home"
          className="mr-7 flex items-center gap-2 no-underline"
        >
          <span className="flex h-5 w-5 items-center justify-center rounded-[6px] bg-primary-text text-[12px] font-extrabold leading-none text-bg">
            b
          </span>
          <span className="font-sans text-[16px] font-bold tracking-[-0.01em] text-primary-text">
            baskr
          </span>
        </a>
        <a
          href="#/flagged"
          className={`${active === "flagged" ? activeLinkClass : linkClass} ml-7`}
        >
          Flagged Papers
        </a>
      </div>

      <div className="flex items-center justify-self-center">
        <form
          onSubmit={handleSubmit}
          role="search"
          className="search-pill flex items-center justify-start gap-2 overflow-hidden rounded-[20px] border border-white/20 bg-transparent py-1.5 pl-[14px] pr-3 font-sans text-[14px] tracking-[0.01em] text-secondary-text focus-within:border-white/40 focus-within:bg-white/[0.06] hover:border-white/40 hover:bg-white/[0.06]"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="flex-shrink-0"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a research question…"
            aria-label="Search papers"
            className="w-full min-w-0 bg-transparent text-[14px] tracking-[0.01em] text-primary-text outline-none placeholder:text-secondary-text"
          />
        </form>
      </div>

      <div className="flex items-center justify-self-end">
        <a
          href="#/lab-context"
          className={active === "labContext" ? activeLinkClass : linkClass}
        >
          Lab Context
        </a>
      </div>
    </nav>
  );
}
