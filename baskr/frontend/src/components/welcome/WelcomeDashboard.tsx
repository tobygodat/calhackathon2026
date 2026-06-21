// Welcome / home screen (handoff "Main Welcome Screen").
// Greets the user, then surfaces newly-relevant papers grouped by the
// relationship they have to the lab's work, one accent colour per column.
import TopNav from "./TopNav";
import DocThumbnail from "./DocThumbnail";

interface WelcomeCard {
  category: string; // bold accent label
  source: string; // institution / author shown as the in-text link
  sourceUrl: string;
  // Copy that follows the source link. Kept separate so the link renders inline.
  description: string;
  // Accent colour, as static Tailwind classes (Tailwind can't build these
  // dynamically). Each card owns one column of the grid.
  borderClass: string;
  labelClass: string;
  linkClass: string;
}

// Hardcoded for the demo; mirrors the four classification labels. Wire to
// the backend (one card per top hit) when the digest endpoint is live.
const CARDS: WelcomeCard[] = [
  {
    category: "Contradiction published",
    source: "Stanford",
    sourceUrl: "#",
    description: " found the Earth to be entirely flat (even at the equator)",
    borderClass: "border-coral",
    labelClass: "text-coral",
    linkClass: "text-coral",
  },
  {
    category: "Knowledge gap filled",
    source: "Charles Darwin's",
    sourceUrl: "#",
    description: " new theory could explain PSL",
    borderClass: "border-amber",
    labelClass: "text-amber",
    linkClass: "text-amber",
  },
  {
    category: "Previous finding reinforced",
    source: "Anthropic's",
    sourceUrl: "#",
    description: " latest paper supports your finding",
    borderClass: "border-teal",
    labelClass: "text-teal",
    linkClass: "text-teal",
  },
  {
    category: "Answer to open question",
    source: "Newton",
    sourceUrl: "#",
    description: " might've finally found out how babies are made",
    borderClass: "border-violet",
    labelClass: "text-violet",
    linkClass: "text-violet",
  },
];

const USER_NAME = "Toby"; // TODO: from auth/user profile

export default function WelcomeDashboard() {
  return (
    <div className="flex h-screen flex-col">
      <TopNav />

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

        {/* Paper cards — three aligned rows (thumbnails, labels, descriptions).
            Rendered as three passes so each row lines up across all columns. */}
        <div className="grid w-full max-w-[860px] grid-cols-4 gap-x-7 gap-y-[13px]">
          {CARDS.map((card) => (
            <div
              key={`thumb-${card.category}`}
              className={`h-[200px] overflow-hidden border-[3px] bg-white ${card.borderClass}`}
            >
              <DocThumbnail />
            </div>
          ))}

          {CARDS.map((card) => (
            <div
              key={`label-${card.category}`}
              className={`text-center font-serif text-[13px] font-bold leading-[1.3] ${card.labelClass}`}
            >
              {card.category}
            </div>
          ))}

          {CARDS.map((card) => (
            <p
              key={`desc-${card.category}`}
              className="text-center font-serif text-[12px] leading-[1.65] text-navy"
            >
              <a
                href={card.sourceUrl}
                className={`underline ${card.linkClass}`}
              >
                {card.source}
              </a>
              {card.description}
            </p>
          ))}
        </div>
      </main>
    </div>
  );
}
