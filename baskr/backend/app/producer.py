"""Live Redis Streams producer: DataPipeline -> baskr:new_papers (SPEC §5.5, §6).

The counterpart to ``consumer.py``. Where the consumer XREADs the
``baskr:new_papers`` stream and classifies each paper, this module is the live
*producer*: it pulls fresh multi-source papers via the existing ingestion path
(``ingest.fetch_recent`` -> ``DataPipeline`` over PubMed/arXiv/bioRxiv, with an
offline staged fallback) and XADDs each one onto the stream for the consumer to
react to in real time.

This is what turns Baskr from a batch replay into a live radar:
``scripts/demo_stream.py`` pushes *frozen staged* papers; this pushes papers as
they are fetched, so the agent loop reacts as new work arrives.

Reuse, not reimplementation:
- fetch + adapt  -> ``ingest.fetch_recent`` (Paper -> PaperOut, offline-safe)
- XADD           -> ``streams.add_new_paper``
- connection     -> ``redis_client.get_client``

Idempotency: a Redis Set (``baskr:producer:seen``) records every paper uid already
pushed, so re-runs and overlapping look-back windows never enqueue the same paper
twice (which would make the consumer burn duplicate Claude classifications). Dedup
degrades safe — if the Set op fails, the paper is still pushed rather than dropped.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import SETTINGS, Settings
from .ingest import fetch_recent
from .models import PaperOut
from .streams import add_new_paper

log = logging.getLogger("baskr.producer")

# Redis Set of paper uids already pushed to the stream (producer-side idempotency).
# Namespaced separately from the storage keys (baskr:paper:, baskr:idx:papers,
# baskr:digest:, baskr:new_papers) so it never collides with them.
SEEN_SET_KEY = "baskr:producer:seen"


def _paper_to_fields(paper: PaperOut) -> dict[str, str]:
    """Flatten a ``PaperOut`` to the stream-entry field schema the consumer
    (``consumer._parse_paper``) expects. Mirrors ``scripts/demo_stream.py`` so the
    live and staged producers emit byte-for-byte compatible entries."""
    return {
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


def _is_new(uid: str, settings: Settings) -> bool:
    """Return True if ``uid`` was not seen before (and record it as seen).

    Uses ``SADD``, which returns 1 when the member is newly added and 0 if it was
    already present. Degrades safe: on any Redis error this returns True so the
    paper is still pushed rather than silently dropped.
    """
    from .redis_client import get_client  # noqa: PLC0415 (lazy: keep import light)

    try:
        added = get_client(settings).sadd(SEEN_SET_KEY, uid)
        return bool(added)
    except Exception as exc:  # noqa: BLE001 (dedup must never block ingestion)
        log.warning("producer: dedup check failed for %s (%s) -> pushing anyway",
                    uid, exc)
        return True


def produce_once(query: str, days: int = 1, max_per_source: int = 20,
                 settings: Settings = SETTINGS, *, dedup: bool = True,
                 dry_run: bool = False) -> dict[str, Any]:
    """Fetch one batch of recent papers and XADD the new ones to ``baskr:new_papers``.

    Returns a stats dict::

        {fetched, pushed, skipped_dupe, skipped_no_abstract, ids}

    ``dry_run`` fetches and reports what *would* be pushed without touching Redis
    (no connection required) — useful offline / in CI. Papers without an abstract
    are skipped (the engine has nothing to reason over).
    """
    papers = fetch_recent(query, days, max_per_source=max_per_source, settings=settings)

    # Reaching a source for real data is "contact" — refresh its stable-connection
    # window (mirrors the heartbeat scheduler). Degrades safe.
    try:
        from . import connections  # noqa: PLC0415
        for source in {p.source for p in papers if p.source in connections.SOURCES}:
            connections.record_contact(source, settings)
    except Exception:  # noqa: BLE001
        pass

    pushed: list[str] = []
    skipped_dupe = 0
    skipped_no_abstract = 0

    for paper in papers:
        if not (paper.abstract and paper.abstract.strip()):
            skipped_no_abstract += 1
            continue

        uid = paper.uid or f"{paper.source}:{paper.source_id}"

        if dry_run:
            pushed.append(uid)
            log.info("producer[dry-run]: would push %s %r", uid, paper.title[:60])
            continue

        if dedup and not _is_new(uid, settings):
            skipped_dupe += 1
            log.debug("producer: skip duplicate %s", uid)
            continue

        msg_id = add_new_paper(_paper_to_fields(paper), settings)
        pushed.append(msg_id)
        log.info("producer: XADD %s [%s] %r", uid, msg_id, paper.title[:60])

    stats: dict[str, Any] = {
        "fetched": len(papers),
        "pushed": len(pushed),
        "skipped_dupe": skipped_dupe,
        "skipped_no_abstract": skipped_no_abstract,
        "ids": pushed,
    }
    log.info("producer: cycle done — %s",
             {k: v for k, v in stats.items() if k != "ids"})
    return stats


def produce_loop(query: str, days: int = 1, max_per_source: int = 20,
                 interval_s: float = 60.0, settings: Settings = SETTINGS,
                 *, dedup: bool = True, max_cycles: int | None = None) -> None:
    """Run ``produce_once`` on a fixed interval — the continuous live-radar mode.

    Blocks until interrupted (Ctrl-C) or ``max_cycles`` cycles have run. Each cycle
    is independent: a transient fetch failure falls back to staged papers inside
    ``fetch_recent``, and an unexpected error in one cycle is logged without killing
    the loop.
    """
    import time  # noqa: PLC0415

    cycle = 0
    try:
        while max_cycles is None or cycle < max_cycles:
            cycle += 1
            log.info("producer: cycle %d (query=%r days=%d)", cycle, query, days)
            try:
                produce_once(query, days, max_per_source, settings, dedup=dedup)
            except Exception as exc:  # noqa: BLE001 (one bad cycle shouldn't stop the radar)
                log.warning("producer: cycle %d failed (%s)", cycle, exc)
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(interval_s)
    except KeyboardInterrupt:
        log.info("producer: stopped after %d cycle(s)", cycle)
