// Fixed 56px top nav (handoff "Top Navigation Bar").
// Shared across the Research Dashboard and Lab Context pages.
// Left/right serif links, a centre group (home icon + search pill that expands
// on hover). `active` highlights the link for the current page.

const linkClass =
  "font-serif text-[14px] tracking-[0.01em] text-steel no-underline transition-colors duration-200 hover:text-pale-ice";
const activeLinkClass =
  "font-serif text-[14px] tracking-[0.01em] text-pale-ice no-underline transition-colors duration-200 hover:text-pale-ice";

interface TopNavProps {
  // Which page is rendering this nav, so its link shows the active colour.
  active?: "dashboard" | "labContext";
}

export default function TopNav({ active }: TopNavProps) {
  return (
    <nav className="flex h-14 flex-shrink-0 items-center justify-between bg-navy px-5">
      <div className="flex items-center">
        <a href="#" className={linkClass}>
          Preferences
        </a>
        <a href="#" className={`${linkClass} ml-7`}>
          Flagged Papers
        </a>
      </div>

      <div className="flex flex-1 items-center justify-center gap-[14px]">
        <a
          href="#/"
          title="Back to dashboard"
          aria-label="Back to dashboard"
          className="flex flex-shrink-0 items-center justify-center text-steel transition-colors duration-200 hover:text-pale-ice"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M3 10.5L12 3l9 7.5" />
            <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
          </svg>
        </a>

        <button
          type="button"
          className="search-pill flex items-center justify-start gap-2 overflow-hidden rounded-[20px] border border-white/15 bg-white/[0.07] py-1.5 pl-[14px] pr-3 font-serif text-[14px] tracking-[0.01em] text-ice hover:border-white/30 hover:bg-white/[0.13] hover:text-pale-ice"
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
          <span className="whitespace-nowrap">Search</span>
        </button>
      </div>

      <div className="flex items-center">
        <a href="#" className={`${linkClass} mr-7`}>
          Past Papers
        </a>
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
