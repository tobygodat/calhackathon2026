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

from . import llm, memory
from .config import SETTINGS, Settings
from .embeddings import embed_text
from .models import Classification, PaperOut, Profile, SearchHit, label_rank
from .prompts import build_prompt


def classify_paper(paper: PaperOut, profile: Profile,
                   settings: Settings = SETTINGS) -> Classification:
    """Run the 5-step engine for one paper against the lab profile (SPEC §6).

    ``profile`` is the lab context (from ``memory.load_profile``); step 2 narrows it
    to the semantic top-k via ``memory.retrieve_relevant`` before prompting.
    """
    # 1. embed the abstract (kept for the semantic contract; the retrieval call
    #    below re-embeds via the same deterministic/OpenAI path).
    embed_text(paper.abstract, settings)

    # 2. retrieve top-k profile items semantically against title + abstract.
    query = f"{paper.title} {paper.abstract}".strip()
    items = memory.retrieve_relevant(query, k=settings.memory_top_k, settings=settings)

    # 3. build the (system, user) prompt (SPEC §7).
    system, user = build_prompt(items, paper)

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
