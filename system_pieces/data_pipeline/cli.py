"""Command-line entry point for the data pipeline.

Examples:
    python -m implementations.data_pipeline.cli "gut microbiome immunotherapy"
    python -m implementations.data_pipeline.cli "amyloid clearance" --days 3 --sources pubmed,biorxiv
    python -m implementations.data_pipeline.cli --check        # show API-key readiness
    python -m implementations.data_pipeline.cli "tau" --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import sentry_sdk

from .config import CONFIG
from .pipeline import DataPipeline
from .sources import SOURCE_REGISTRY


def _print_status() -> None:
    print("Data pipeline configuration / API-key readiness:\n")
    for key, val in CONFIG.status().items():
        print(f"  {key:24} {val}")
    print(f"\n  Available sources: {', '.join(sorted(SOURCE_REGISTRY))}")


def main(argv: list[str] | None = None) -> int:
    # Initialize error monitoring as early as possible so any failure during a
    # pipeline run is reported. Enabled only when SENTRY_DSN is set (see
    # .env.example); unset is a clean no-op for local/dev runs.
    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            # Add data like request headers and IP for users; see
            # https://docs.sentry.io/platforms/python/data-management/data-collected/
            send_default_pii=True,
        )

    parser = argparse.ArgumentParser(prog="baskr-pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="search query / lab open question")
    parser.add_argument("--days", type=int, default=CONFIG.default_lookback_days,
                        help=f"lookback window in days (default {CONFIG.default_lookback_days})")
    parser.add_argument("--max", type=int, default=CONFIG.default_max_per_source,
                        dest="max_per_source", help="max papers per source")
    parser.add_argument("--sources", default=None,
                        help=f"comma-separated subset of: {','.join(SOURCE_REGISTRY)}")
    parser.add_argument("--json", dest="json_out", metavar="PATH",
                        help="write full results to a JSON file")
    parser.add_argument("--check", action="store_true", help="print key readiness and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.check:
        _print_status()
        return 0

    if not args.query:
        parser.error("a query is required (or use --check)")

    sources = args.sources.split(",") if args.sources else None
    pipe = DataPipeline(sources=sources)
    result = pipe.fetch(args.query, days=args.days, max_per_source=args.max_per_source)

    # console summary
    print(f"\nQuery: {args.query!r}   window: last {args.days} days")
    print(f"Sources: {result.counts}")
    if result.errors:
        print(f"Errors:  {result.errors}")
    print(f"Unique papers after dedupe: {len(result.papers)}\n")

    for i, p in enumerate(result.papers[:25], 1):
        flag = "" if p.has_abstract else "  [no abstract]"
        print(f"{i:>3}. [{p.source}] {p.citation()}{flag}")

    if args.json_out:
        payload = {
            "query": args.query,
            "days": args.days,
            "counts": result.counts,
            "errors": result.errors,
            "papers": [p.to_dict() for p in result.papers],
        }
        with open(args.json_out, "w") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"\nWrote {len(result.papers)} papers -> {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
