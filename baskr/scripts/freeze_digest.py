"""Offline: generate + write N days of frozen digest (SPEC §6 Digest path).

For each target date: fetch recent papers (via the existing ``DataPipeline``),
run ``engine.run_digest``, keep non-NOT_RELEVANT hits, and persist them to both
``baskr:digest:{date}`` (Redis) and ``data/digest_frozen/{date}.json``.

Run:  python scripts/freeze_digest.py [--days 5] [--query "gut microbiome"]
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

# Make the baskr/backend package importable from anywhere.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import SETTINGS
from app.engine import run_digest
from app.ingest import fetch_recent
from app.redis_client import store_digest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("freeze_digest")

DIGEST_DIR = Path(__file__).resolve().parents[1] / "data" / "digest_frozen"
DEFAULT_QUERY = "gut microbiome bacteria"


def freeze_day(date: str, query: str = DEFAULT_QUERY) -> int:
    """Generate and persist the frozen digest for one date. Returns hit count."""
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)

    papers = fetch_recent(query, days=7, settings=SETTINGS)
    hits = run_digest(date, papers, SETTINGS)

    entries = [
        {
            "date": date,
            "paper": h.paper.model_dump(),
            "classification": h.classification.model_dump(),
        }
        for h in hits
    ]
    payload = json.dumps(entries, indent=2)

    # Persist to filesystem.
    out_path = DIGEST_DIR / f"{date}.json"
    out_path.write_text(payload)
    log.info("Wrote %d entries -> %s", len(entries), out_path)

    # Persist to Redis (best-effort; may fail in degraded mode).
    try:
        store_digest(date, payload, SETTINGS)
        log.info("Stored digest in Redis: baskr:digest:%s", date)
    except Exception as exc:  # noqa: BLE001
        log.warning("Redis store skipped (%s: %s)", type(exc).__name__, exc)

    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate frozen Baskr digests.")
    parser.add_argument("--days", type=int, default=5, help="number of recent days")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="search query for paper fetch")
    args = parser.parse_args()

    today = datetime.date.today()
    total = 0
    for i in range(args.days):
        date = (today - datetime.timedelta(days=i)).isoformat()
        count = freeze_day(date, query=args.query)
        print(f"  {date}: {count} hits")
        total += count

    print(f"\nFroze {args.days} days, {total} total entries.")


if __name__ == "__main__":
    main()
