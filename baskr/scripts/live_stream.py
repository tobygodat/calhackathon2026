"""Live producer: fetch fresh multi-source papers and push them to baskr:new_papers.

The live counterpart to ``demo_stream.py`` (which replays *frozen staged* papers).
This pulls recent papers through the multi-source ``DataPipeline`` (PubMed / arXiv
/ bioRxiv, with an offline staged fallback) and XADDs each new one onto the
``baskr:new_papers`` stream, where the agent consumer classifies it live.

Run it alongside the FastAPI server to see real-time alerts in the dev UI's SSE
feed and the stream-length metric climb.

Usage:
  python scripts/live_stream.py --query "gut microbiome" --days 1
  python scripts/live_stream.py --loop --interval 60          # continuous radar
  python scripts/live_stream.py --dry-run                     # fetch only, no Redis
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make both the repo root (for ``system_pieces.data_pipeline``) and the
# ``baskr/backend`` package (for ``app.*``) importable — mirrors demo_stream.py
# but also adds the root so the *live* pipeline import resolves.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _BACKEND):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load_dotenv(path: Path) -> None:
    """Minimal stdlib .env loader: apply ``KEY=VALUE`` lines into ``os.environ``
    without overriding values already exported in the real environment. Must run
    *before* ``app.config`` is imported, since ``Settings`` reads ``os.environ`` at
    import time. Quotes around values are stripped; ``#`` lines are ignored."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Drop any trailing inline comment, then surrounding quotes.
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


# Pick up baskr/.env (gitignored) so REDIS_URL etc. are loaded automatically.
_load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.config import SETTINGS
from app.producer import produce_loop, produce_once

DEFAULT_QUERY = "gut microbiome"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push live multi-source papers to the baskr:new_papers stream.")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Search query")
    parser.add_argument("--days", type=int, default=1, help="Look-back window in days")
    parser.add_argument("--max-per-source", type=int, default=20,
                        help="Max papers fetched per source")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously (live radar) instead of one batch")
    parser.add_argument("--interval", type=float, default=60.0,
                        help="Seconds between cycles in --loop mode")
    parser.add_argument("--no-dedup", action="store_true",
                        help="Disable producer-side dedup (push everything)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and report what would be pushed; no Redis writes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.loop:
        print(f"Live radar: query={args.query!r} every {args.interval:g}s "
              f"(Ctrl-C to stop)…")
        produce_loop(args.query, days=args.days, max_per_source=args.max_per_source,
                     interval_s=args.interval, settings=SETTINGS,
                     dedup=not args.no_dedup)
        return

    mode = "dry-run" if args.dry_run else "live"
    print(f"Producing one batch ({mode}): query={args.query!r} days={args.days}…")
    stats = produce_once(args.query, days=args.days,
                         max_per_source=args.max_per_source, settings=SETTINGS,
                         dedup=not args.no_dedup, dry_run=args.dry_run)
    print(f"\nfetched={stats['fetched']} pushed={stats['pushed']} "
          f"skipped_dupe={stats['skipped_dupe']} "
          f"skipped_no_abstract={stats['skipped_no_abstract']}")


if __name__ == "__main__":
    main()
