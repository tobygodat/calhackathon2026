"""Classification engine — implemented once, shared by both surfaces (SPEC §6).

    classify_paper(paper, profile):
      1. embed(paper.abstract)                          # embeddings.py / OpenAI
      2. retrieve top-k profile items from memory       # memory.py
      3. build_prompt(profile_items, paper)             # prompts.py (§7)
      4. Claude -> {label, reason, matched_item_id, confidence}   # llm.py
      5. return classification

Paper fetching is delegated to ingest.py (DataPipeline adapter).
"""

from __future__ import annotations

from .config import SETTINGS, Settings
from .models import Classification, Label, PaperOut, Profile, SearchHit


def classify_paper(paper: PaperOut, profile: Profile,
                   settings: Settings = SETTINGS) -> Classification:
    """Run the 5-step engine for one paper against the lab profile (SPEC §6)."""
    from .embeddings import embed_text
    from .llm import classify
    from .memory import retrieve_relevant
    from .prompts import build_prompt

    # Step 1: embed the paper abstract (skip if empty)
    if paper.abstract:
        try:
            embed_text(paper.abstract, settings=settings)
        except Exception:
            pass  # embedding is optional for prompt-based classification

    # Step 2: retrieve relevant profile items
    items = retrieve_relevant(paper.abstract or paper.title, settings=settings)

    # Step 3: build prompt
    system, user = build_prompt(items, paper)

    # Step 4: call Claude
    classification = classify(system, user, settings=settings)

    return classification


def active_search(question: str, settings: Settings = SETTINGS) -> list[SearchHit]:
    """Live surface: fetch recent papers, classify each, return relevant hits."""
    from .ingest import fetch_recent
    from .memory import load_profile

    profile = load_profile(settings=settings)

    # Build a gut-microbiome focused query combining the user question
    gut_query = f"gut microbiome {question}" if "microbiome" not in question.lower() else question

    papers = fetch_recent(
        query=gut_query,
        days=settings.active_search_days,
        max_per_source=20,
        settings=settings,
    )

    hits: list[SearchHit] = []
    for paper in papers:
        try:
            classification = classify_paper(paper, profile, settings=settings)
        except Exception as exc:
            # If classification fails (e.g., no API key), mark as NOT_RELEVANT
            classification = Classification(
                label=Label.NOT_RELEVANT,
                reason=f"Classification unavailable: {exc}",
                matched_item_id=None,
                confidence=0.0,
            )

        if classification.label != Label.NOT_RELEVANT:
            hits.append(SearchHit(paper=paper, classification=classification))

    # Sort by confidence descending, cap at active_search_cap
    hits.sort(key=lambda h: h.classification.confidence, reverse=True)
    return hits[: settings.active_search_cap]


def run_digest(date: str, papers: list[PaperOut],
               settings: Settings = SETTINGS) -> list[SearchHit]:
    """Offline surface: classify a day's papers, keep non-NOT_RELEVANT hits."""
    from .memory import load_profile

    profile = load_profile(settings=settings)
    hits: list[SearchHit] = []
    for paper in papers:
        try:
            classification = classify_paper(paper, profile, settings=settings)
        except Exception:
            classification = Classification(
                label=Label.NOT_RELEVANT,
                reason="Classification unavailable.",
                matched_item_id=None,
                confidence=0.0,
            )
        if classification.label != Label.NOT_RELEVANT:
            hits.append(SearchHit(paper=paper, classification=classification))
    return hits
