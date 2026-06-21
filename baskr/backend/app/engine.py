"""Classification engine — implemented once, shared by both surfaces (SPEC §6).

    classify_paper(paper, profile):
      1. embed(paper.abstract)                          # embeddings.py / OpenAI
      2. retrieve top-k profile items from Agent Memory # memory.py, semantic, k≈8
      3. build_prompt(profile_items, paper)             # prompts.py (§7)
      4. Claude -> {label, reason, matched_item_id, confidence}   # llm.py
      5. return classification

Paper *fetching* is delegated to the existing multi-source pipeline rather than a
local PubMed module: ``DataPipeline`` (system_pieces/data_pipeline) returns
normalized, deduped ``Paper`` objects across PubMed/arXiv/bioRxiv. Active Search
and the offline Digest are thin callers of ``classify_paper``.

Import note: ``DataPipeline`` is imported from the repo-root ``system_pieces``
package; ``app.__init__`` puts the repo root on ``sys.path``. Keep the import local
to the functions that need it to avoid a hard import at module load.
"""

from __future__ import annotations

import logging

from . import llm, memory
from .config import SETTINGS, Settings
from .embeddings import embed_text
from .models import Classification, PaperOut, Profile, SearchHit, label_rank
from .prompts import build_prompt

log = logging.getLogger("baskr.engine")


def _retrieve_prior_work(embedding: list[float], paper: PaperOut,
                         settings: Settings) -> list[dict]:
    """Top-k semantically-similar prior papers from the RedisVL corpus index
    (``query_similar``), excluding the paper itself. Degrades safe: returns ``[]`` if
    the corpus / Redis is unavailable, so classification still runs offline."""
    from .redis_client import query_similar  # noqa: PLC0415 (local: keep boot light)

    self_uid = paper.uid or f"{paper.source}:{paper.source_id}"
    try:
        # over-fetch by one so the paper itself (if already indexed) can be dropped.
        records = query_similar(embedding, settings.corpus_top_k + 1, settings)
    except Exception as exc:  # noqa: BLE001 (corpus is optional prompt context)
        log.debug("prior-work retrieval skipped (%s: %s)", type(exc).__name__, exc)
        return []
    prior = [r for r in records if r.get("uid") != self_uid]
    return prior[: settings.corpus_top_k]


def classify_paper(paper: PaperOut, profile: Profile,
                   settings: Settings = SETTINGS) -> Classification:
    """Run the engine for one paper against the lab profile + corpus (SPEC §6).

    ``profile`` is the lab context (from ``memory.load_profile``); step 2 narrows it
    to the semantic top-k via ``memory.retrieve_relevant``. Step 2b pulls the most
    similar prior papers from the RedisVL vector corpus (``query_similar``) so Claude
    can weigh novelty/overlap against work the lab has already seen.
    """
    # 1. embed the abstract — reused for the corpus vector search in step 2b.
    embedding = embed_text(paper.abstract, settings)

    # 2. retrieve top-k profile items semantically against title + abstract.
    query = f"{paper.title} {paper.abstract}".strip()
    items = memory.retrieve_relevant(query, k=settings.memory_top_k, settings=settings)

    # 2b. retrieve semantically-similar prior papers from the vector corpus.
    prior_work = _retrieve_prior_work(embedding, paper, settings)

    # 3. build the (system, user) prompt (SPEC §7) with profile + prior work.
    system, user = build_prompt(items, paper, prior_work=prior_work)

    # 4 + 5. Claude (or degraded fallback) -> parsed, threshold-collapsed Classification.
    return llm.classify(system, user, settings)


def _sort_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """Sort hits across the four relationship labels: by label priority
    (``label_rank``: CONTRADICTS -> VERIFIES -> EXTENDS -> TANGENTIAL; SCOOP just
    after CONTRADICTS), then by confidence descending within each label."""
    return sorted(
        hits,
        key=lambda h: (label_rank(h.classification.label),
                       -h.classification.confidence),
    )


def active_search(question: str, settings: Settings = SETTINGS) -> list[SearchHit]:
    """Live surface: fetch recent papers via ``DataPipeline``, classify each against
    the profile (``memory.load_profile``), and return them sorted across all four
    relationship labels (``_sort_hits``), capped at ``active_search_cap``.

        from system_pieces.data_pipeline import DataPipeline
    """
    from .ingest import fetch_recent  # noqa: PLC0415  (local: keep app boot light)

    papers = fetch_recent(question, settings.active_search_days, settings=settings)
    profile = memory.load_profile(settings)

    hits = [
        SearchHit(paper=paper, classification=classify_paper(paper, profile, settings))
        for paper in papers
    ]
    return _sort_hits(hits)[: settings.active_search_cap]


def run_digest(date: str, papers: list[PaperOut],
               settings: Settings = SETTINGS) -> list[SearchHit]:
    """Offline surface: classify a day's papers and return all four sorts ordered by
    ``_sort_hits`` (CONTRADICTS -> VERIFIES -> EXTENDS -> TANGENTIAL, confidence desc
    within each). Callers persist the result (see scripts/freeze_digest.py)."""
    profile = memory.load_profile(settings)

    hits = [
        SearchHit(paper=paper, classification=classify_paper(paper, profile, settings))
        for paper in papers
    ]
    return _sort_hits(hits)
