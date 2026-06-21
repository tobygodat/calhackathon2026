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

from .config import SETTINGS, Settings
from .models import Classification, PaperOut, Profile, SearchHit


def classify_paper(paper: PaperOut, profile: Profile,
                   settings: Settings = SETTINGS) -> Classification:
    """Run the 5-step engine for one paper against the lab profile (SPEC §6).

    ``profile`` is the lab context (from ``memory.load_profile``); step 2 narrows it
    to the semantic top-k via ``memory.retrieve_relevant`` before prompting.
    """
    raise NotImplementedError


def active_search(question: str, settings: Settings = SETTINGS) -> list[SearchHit]:
    """Live surface: fetch recent papers via ``DataPipeline``, classify each against
    the profile (``memory.load_profile``), return non-NOT_RELEVANT hits sorted by
    confidence, capped at ``active_search_cap``.

        from system_pieces.data_pipeline import DataPipeline
    """
    raise NotImplementedError


def run_digest(date: str, papers: list[PaperOut],
               settings: Settings = SETTINGS) -> list[SearchHit]:
    """Offline surface: classify a day's papers, keep non-NOT_RELEVANT hits.
    Callers persist the result (see scripts/freeze_digest.py)."""
    raise NotImplementedError
