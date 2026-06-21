// Paper thumbnail. We intentionally do NOT render the PDF's first page anymore:
// fetching /api/thumbnail downloads a full PDF and renders it server-side, which
// slowed card load. Always show the lightweight placeholder skeleton instead.
import type { Paper } from "../../types";
import DocThumbnail from "./DocThumbnail";

// `paper` is kept for the call-site interface (and so this can re-enable real
// thumbnails later) even though it's unused while we always show the skeleton.
export default function PaperThumbnail({ paper: _paper }: { paper: Paper }) {
  return <DocThumbnail />;
}
