"""Paper ingestion: fetch -> embed -> bulk-load RedisVL (SPEC §6 Digest path).

Paper fetching is delegated to system_pieces/data_pipeline (DataPipeline).
This module adapts its Paper objects to PaperOut and optionally embeds them.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import SETTINGS, Settings
from .models import PaperOut

# Make system_pieces importable regardless of how uvicorn is started.
_REPO_ROOT = Path(__file__).resolve().parents[3]  # app/ -> backend/ -> baskr/ -> calhackathon2026/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _pipeline_paper_to_out(p: object) -> PaperOut:
    """Convert a data_pipeline.Paper to a PaperOut."""
    return PaperOut(
        source=p.source,          # type: ignore[attr-defined]
        source_id=p.source_id,    # type: ignore[attr-defined]
        title=p.title,            # type: ignore[attr-defined]
        abstract=p.abstract or "", # type: ignore[attr-defined]
        authors=list(p.authors or []), # type: ignore[attr-defined]
        doi=p.doi,                # type: ignore[attr-defined]
        url=p.url,                # type: ignore[attr-defined]
        journal=p.journal,        # type: ignore[attr-defined]
        published=p.published,    # type: ignore[attr-defined]
        categories=list(p.categories or []), # type: ignore[attr-defined]
        uid=p.uid,                # type: ignore[attr-defined]
    )


def fetch_recent(query: str, days: int, max_per_source: int = 50,
                 settings: Settings = SETTINGS) -> list[PaperOut]:
    """Pull recent papers across sources via DataPipeline and adapt to PaperOut."""
    from system_pieces.data_pipeline import DataPipeline
    pipeline = DataPipeline(sources=["pubmed", "arxiv", "biorxiv"])
    result = pipeline.fetch(query, days=days, max_per_source=max_per_source)
    return [_pipeline_paper_to_out(p) for p in result.papers]


def ingest(query: str, days: int, settings: Settings = SETTINGS) -> int:
    """Fetch -> embed abstracts -> upsert into the RedisVL index. Returns count."""
    from .embeddings import embed_batch
    from .redis_client import upsert_paper

    papers = fetch_recent(query, days, settings=settings)
    if not papers:
        return 0

    texts = [p.abstract for p in papers if p.abstract]
    embeddings = embed_batch(texts, settings=settings)

    embed_idx = 0
    for paper in papers:
        if not paper.abstract:
            continue
        emb = embeddings[embed_idx]
        embed_idx += 1
        fields = paper.model_dump(exclude={"uid"})
        uid = paper.uid or f"{paper.source}:{paper.source_id}"
        upsert_paper(uid, fields, emb, settings=settings)

    return embed_idx
