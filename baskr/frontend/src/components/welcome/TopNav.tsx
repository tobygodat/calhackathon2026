// Fixed 56px top nav (handoff "Shared Top Nav Bar").
// Shared across the Research Dashboard and Lab Context pages.
// Left/right monochrome links and a centre search pill that expands on hover.
// The pill is a live search form: type a research question and Enter runs the
// active-query search (#/search?q=…). `active` highlights the current page.
import { useState } from "react";

// One cell of the right-side segmented nav group. `active` fills the cell to
// mark the current page; `divider` adds the right-hand separator between cells.
function navCellClass(active: boolean, divider: boolean): string {
  return [
    "px-[18px] py-2 font-sans text-[14px] tracking-[0.01em] no-underline transition-colors duration-200",
    divider ? "border-r border-white/15" : "",
    active
      ? "bg-white/[0.08] text-primary-text"
      : "text-muted-text hover:bg-white/[0.05] hover:text-primary-text",
  ].join(" ");
}

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
    <nav className="grid h-14 flex-shrink-0 grid-cols-[auto_1fr_auto] items-center gap-8 border-b border-divider bg-bg px-6">
      <div className="flex items-center justify-self-start">
        {/* Wordmark doubles as the home link (replaces the old top-right house).
            Nudged right off the edge so it doesn't sit flush against the border. */}
        <a
          href="#/"
          aria-label="Baskr home"
          className="ml-2 flex items-center gap-2 no-underline"
        >
          <img
            src="/shark-logo-white.png"
            alt=""
            aria-hidden="true"
            className="h-[22px] w-auto"
          />
          <span className="font-sans text-[16px] font-bold tracking-[-0.01em] text-primary-text">
            baskr
          </span>
        </a>
      </div>

      <div className="flex items-center justify-self-stretch">
        <form
          onSubmit={handleSubmit}
          role="search"
          className="search-pill mx-auto flex w-full max-w-[760px] items-center justify-start gap-2 overflow-hidden rounded-[20px] border border-white/20 bg-transparent py-2 pl-[16px] pr-3 font-sans text-[14px] tracking-[0.01em] text-secondary-text focus-within:border-white/40 focus-within:bg-white/[0.06] hover:border-white/40 hover:bg-white/[0.06]"
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

      {/* Segmented button group (handoff reference): Papers + Lab Context share
          one bordered, rounded container with an internal divider. The active
          page reads as the selected cell via a filled background. */}
      <div className="flex items-center justify-self-end">
        <div className="flex items-center overflow-hidden rounded-[12px] border border-white/20 bg-white/[0.02]">
          <a href="#/flagged" className={navCellClass(active === "flagged", true)}>
            Papers
          </a>
          <a
            href="#/lab-context"
            className={navCellClass(active === "labContext", false)}
          >
            Lab Context
          </a>
        </div>
      </div>
    </nav>
  );
}
