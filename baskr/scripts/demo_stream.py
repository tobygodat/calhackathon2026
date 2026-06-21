"""Push staged gut-microbiome papers into the baskr:new_papers stream.

Run this while the FastAPI server is running to trigger real-time classification
alerts visible in the dev UI's SSE feed.

Usage:  python scripts/demo_stream.py [--count N] [--delay SECS]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Make the baskr/backend package importable.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import SETTINGS
from app.ingest import _load_staged_papers
from app.streams import add_new_paper


def main() -> None:
    parser = argparse.ArgumentParser(description="Push staged papers to baskr:new_papers stream.")
    parser.add_argument("--count", type=int, default=0, help="Max papers to push (0 = all)")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between pushes")
    args = parser.parse_args()

    papers = _load_staged_papers()
    if args.count > 0:
        papers = papers[: args.count]

    print(f"Pushing {len(papers)} papers to baskr:new_papers …")
    for paper in papers:
        fields = {
            "uid": paper.uid or f"{paper.source}:{paper.source_id}",
            "source": paper.source,
            "source_id": paper.source_id,
            "title": paper.title,
            "abstract": paper.abstract,
            "authors": json.dumps(paper.authors),
            "doi": paper.doi or "",
            "url": paper.url or "",
            "journal": paper.journal or "",
            "published": paper.published or "",
        }
        msg_id = add_new_paper(fields, SETTINGS)
        print(f"  [{msg_id}] {paper.title[:60]!r}")
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"\nDone — pushed {len(papers)} papers.")


if __name__ == "__main__":
    main()
