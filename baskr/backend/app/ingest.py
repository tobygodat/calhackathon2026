"""Paper ingestion: fetch -> embed -> bulk-load RedisVL (SPEC §6 Digest path).

Replaces the spec's local ``pubmed.py``: the *fetch* step is delegated to the
existing multi-source ``DataPipeline`` (system_pieces/data_pipeline), which
already does esearch/efetch plus arXiv/bioRxiv and cross-source dedupe.
This module only adds the embed + Redis bulk-load on top.

    from system_pieces.data_pipeline import DataPipeline

Offline robustness
------------------
Live source fetches hit PubMed/arXiv/bioRxiv over the network, which is
EGRESS-BLOCKED in this sandbox (NCBI returns 403). ``fetch_recent`` therefore tries
``DataPipeline`` under a short timeout and, on ANY error / timeout / empty result,
falls back to a small set of STAGED gut-microbiome sample papers
(``data/sample_papers.json``) so ingest / active_search stay runnable and demoable
offline. The path actually used is logged ("datapipeline" vs "staged_fallback").
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from .config import SETTINGS, Settings
from .embeddings import embed_batch
from .models import PaperOut
from .redis_client import upsert_paper

log = logging.getLogger("baskr.ingest")

# data/sample_papers.json relative to the baskr/ repo root (parents[2] == baskr/).
SAMPLE_PAPERS_PATH = Path(__file__).resolve().parents[2] / "data" / "sample_papers.json"

# Hard ceiling on the (potentially hanging) live network fetch, in seconds.
_FETCH_TIMEOUT_S = 8.0


def _load_staged_papers() -> list[PaperOut]:
    """Load the offline STAGED fallback papers (``data/sample_papers.json``)."""
    raw = json.loads(SAMPLE_PAPERS_PATH.read_text())
    return [PaperOut(**record) for record in raw]


def _adapt_paper(paper) -> PaperOut:
    """Adapt a ``data_pipeline.Paper`` to ``PaperOut`` (mirrors ``Paper.to_dict()``)."""
    return PaperOut(
        source=paper.source,
        source_id=paper.source_id,
        title=paper.title,
        abstract=paper.abstract,
        authors=list(paper.authors),
        doi=paper.doi,
        url=paper.url,
        journal=paper.journal,
        published=paper.published,
        categories=list(paper.categories),
        uid=paper.uid,
    )


def _fetch_via_pipeline(query: str, days: int, max_per_source: int) -> list[PaperOut]:
    """Run the live multi-source DataPipeline fetch bounded by a short timeout.

    Returns adapted ``PaperOut`` records, or raises on any failure/timeout so the
    caller can fall back to staged papers.
    """
    from system_pieces.data_pipeline import DataPipeline  # noqa: PLC0415

    pipeline = DataPipeline()

    def _run():
        return pipeline.fetch(query, days=days, max_per_source=max_per_source)

    # Bound the (possibly hanging) network fan-out so ingest never blocks the demo.
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run)
        result = future.result(timeout=_FETCH_TIMEOUT_S)

    return [_adapt_paper(p) for p in result.papers]


def fetch_recent(query: str, days: int, max_per_source: int = 50,
                 settings: Settings = SETTINGS) -> list[PaperOut]:
    """Pull recent papers across sources via ``DataPipeline`` and adapt each
    ``data_pipeline.Paper`` to ``PaperOut``.

    Robust/offline-safe: tries the live pipeline under a short timeout; on any
    error/timeout/empty result, falls back to the STAGED sample papers so callers
    stay runnable without network. Logs which path was used.
    """
    try:
        papers = _fetch_via_pipeline(query, days, max_per_source)
        if papers:
            log.info("fetch_recent: %d papers via datapipeline (live)", len(papers))
            return papers
        log.warning("fetch_recent: datapipeline returned 0 papers -> staged_fallback")
    except FutureTimeout:
        log.warning("fetch_recent: datapipeline timed out (%.0fs) -> staged_fallback",
                    _FETCH_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001  (any fetch failure -> staged fallback)
        log.warning("fetch_recent: datapipeline failed (%s: %s) -> staged_fallback",
                    type(exc).__name__, exc)

    staged = _load_staged_papers()
    log.info("fetch_recent: %d papers via staged_fallback (offline)", len(staged))
    return staged


def fetch_raw(query: str, days: int, max_per_source: int = 50,
              settings: Settings = SETTINGS,
              ) -> tuple[list[PaperOut], dict[str, int], dict[str, str]]:
    """Like ``fetch_recent`` but also returns per-source counts and errors.

    Returns (papers, counts, errors). On pipeline failure/timeout the staged
    fallback fires and errors will carry the failure reason.
    """
    try:
        from system_pieces.data_pipeline import DataPipeline  # noqa: PLC0415

        pipeline = DataPipeline()

        def _run():
            return pipeline.fetch(query, days=days, max_per_source=max_per_source)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run)
            result = future.result(timeout=_FETCH_TIMEOUT_S)

        if result.papers:
            papers = [_adapt_paper(p) for p in result.papers]
            log.info("fetch_raw: %d papers via datapipeline", len(papers))
            return papers, dict(result.counts), dict(result.errors)
        log.warning("fetch_raw: datapipeline returned 0 papers -> staged_fallback")
        errors: dict[str, str] = {**result.errors, "pipeline": "returned 0 papers"}
    except FutureTimeout:
        log.warning("fetch_raw: datapipeline timed out -> staged_fallback")
        errors = {"pipeline": f"timeout after {_FETCH_TIMEOUT_S:.0f}s"}
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch_raw: datapipeline failed (%s) -> staged_fallback", exc)
        errors = {"pipeline": f"{type(exc).__name__}: {exc}"}

    staged = _load_staged_papers()
    log.info("fetch_raw: %d papers via staged_fallback", len(staged))
    return staged, {"staged": len(staged)}, errors


def ingest(query: str, days: int, settings: Settings = SETTINGS) -> int:
    """Fetch -> embed abstracts -> upsert into the RedisVL index. Returns count."""
    papers = fetch_recent(query, days, settings=settings)
    if not papers:
        return 0

    embeddings = embed_batch([p.abstract for p in papers], settings)
    for paper, embedding in zip(papers, embeddings):
        # uid is stable across sources; fall back to source:source_id if absent.
        uid = paper.uid or f"{paper.source}:{paper.source_id}"
        upsert_paper(uid, paper.model_dump(), embedding, settings)

    return len(papers)
