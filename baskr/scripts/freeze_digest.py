"""Offline: generate + write N days of frozen digest (SPEC §6 Digest path).

For each target date: fetch that day's papers (via the existing ``DataPipeline``),
run ``engine.run_digest``, keep non-NOT_RELEVANT hits, and persist them to both
``baskr:digest:{date}`` (Redis) and ``data/digest_frozen/{date}.json``.

Run:  python scripts/freeze_digest.py --days 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

DIGEST_DIR = Path(__file__).resolve().parents[1] / "data" / "digest_frozen"


def freeze_day(date: str) -> int:
    """Generate and persist the frozen digest for one date. Returns hit count."""
    raise NotImplementedError


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate frozen Baskr digests.")
    parser.add_argument("--days", type=int, default=5, help="number of recent days")
    args = parser.parse_args()  # noqa: F841  (consumed once implemented)
    raise NotImplementedError


if __name__ == "__main__":
    main()
