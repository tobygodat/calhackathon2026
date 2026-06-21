// Real paper thumbnail: first page of the PDF rendered by the backend
// (GET /api/thumbnail). Falls back to the placeholder document skeleton when
// no image is available (PubMed / missing url / render error).
import { useState } from "react";
import type { Paper } from "../../types";
import DocThumbnail from "./DocThumbnail";

// Sources the backend can derive a free PDF for; others go straight to fallback.
const PDF_SOURCES = new Set(["arxiv", "biorxiv"]);

function thumbnailUrl(paper: Paper): string | null {
  if (!paper.url || !PDF_SOURCES.has(paper.source)) return null;
  const params = new URLSearchParams({ source: paper.source, url: paper.url });
  return `/api/thumbnail?${params.toString()}`;
}

export default function PaperThumbnail({ paper }: { paper: Paper }) {
  const src = thumbnailUrl(paper);
  const [errored, setErrored] = useState(false);

  if (!src || errored) {
    return <DocThumbnail />;
  }

  return (
    <img
      src={src}
      alt={paper.title}
      className="block h-full w-full object-cover object-top"
      loading="lazy"
      onError={() => setErrored(true)}
    />
  );
}
