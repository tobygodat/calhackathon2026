// Paper thumbnail — shows the backend-rendered first page if available,
// otherwise falls back to the DocThumbnail skeleton.
import { useState } from "react";
import type { Paper } from "../../types";
import DocThumbnail from "./DocThumbnail";

export default function PaperThumbnail({ paper }: { paper: Paper }) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  if (paper.thumbnail_url && !errored) {
    return (
      <div className="relative h-full w-full">
        {/* Skeleton shown until the image loads */}
        {!loaded && (
          <div className="absolute inset-0">
            <DocThumbnail />
          </div>
        )}
        <img
          src={paper.thumbnail_url}
          alt=""
          aria-hidden="true"
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
          className={`h-full w-full object-cover object-top transition-opacity duration-300 ${
            loaded ? "opacity-100" : "opacity-0"
          }`}
        />
      </div>
    );
  }

  return <DocThumbnail />;
}
