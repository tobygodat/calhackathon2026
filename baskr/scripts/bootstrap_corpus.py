"""Bootstrap the historical paper corpus into RedisVL (build-phases Phase 2).

Orchestrates the corpus load: fetch papers via the multi-source ``DataPipeline``
(with offline staged fallback) -> embed abstracts -> upsert into the
``baskr:idx:papers`` RedisVL index. This is the corpus the engine / active-search
query for semantically similar prior work.

Thin CLI over ``app.ingest`` (the fetch -> embed -> upsert logic already lives in
``ingest.ingest``), mirroring demo_stream.py / live_stream.py / freeze_digest.py.

Usage:
  python scripts/bootstrap_corpus.py --query "gut microbiome" --days 30
  python scripts/bootstrap_corpus.py --dump        # also write data/corpus.json
  python scripts/bootstrap_corpus.py --dry-run     # fetch + report, no embed/Redis
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Make the baskr/backend package importable from anywhere. app.config auto-loads
# baskr/.env on import, so REDIS_URL etc. are picked up without a manual export.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import SETTINGS
from app.ingest import fetch_recent, ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("bootstrap_corpus")

CORPUS_PATH = Path(__file__).resolve().parents[1] / "data" / "corpus.json"
DEFAULT_QUERY = "gut microbiome"


def dump_corpus(query: str, days: int, max_per_source: int) -> int:
    """Fetch the corpus and write it to data/corpus.json (no Redis). Returns count."""
    papers = fetch_recent(query, days, max_per_source=max_per_source, settings=SETTINGS)
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_PATH.write_text(json.dumps([p.model_dump() for p in papers], indent=2))
    log.info("Wrote %d papers -> %s", len(papers), CORPUS_PATH)
    return len(papers)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch papers and load them into the RedisVL corpus index.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="search query")
    parser.add_argument("--days", type=int, default=30, help="look-back window in days")
    parser.add_argument("--max-per-source", type=int, default=100,
                        help="max papers fetched per source")
    parser.add_argument("--dump", action="store_true",
                        help="also write the fetched corpus to data/corpus.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch + report counts only; no embed/Redis writes")
    args = parser.parse_args()

    if args.dry_run:
        papers = fetch_recent(args.query, args.days,
                              max_per_source=args.max_per_source, settings=SETTINGS)
        with_abstract = sum(1 for p in papers if p.abstract and p.abstract.strip())
        print(f"[dry-run] fetched={len(papers)} with_abstract={with_abstract} "
              f"(would upsert into {SETTINGS.papers_index})")
        return

    if args.dump:
        n = dump_corpus(args.query, args.days, args.max_per_source)
        print(f"Dumped {n} papers -> {CORPUS_PATH}")
        return

    loaded = ingest(args.query, args.days, settings=SETTINGS)
    print(f"Loaded {loaded} papers into {SETTINGS.papers_index} "
          f"(query={args.query!r}, days={args.days}).")


if __name__ == "__main__":
    main()
