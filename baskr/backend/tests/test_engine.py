"""Phase 3 UNIT tests for the classification engine (SPEC §6).

No live Redis required: profile retrieval and the LLM call are monkeypatched so the
cap / sort / filter logic in ``active_search`` and ``run_digest`` is asserted
precisely and deterministically.
"""

from __future__ import annotations

import pytest

from app import engine
from app.models import (
    Classification,
    Label,
    PaperOut,
    Profile,
    ProfileItem,
    ProfileItemKind,
)


def _paper(n: int) -> PaperOut:
    return PaperOut(
        source="pubmed",
        source_id=str(n),
        title=f"Paper {n} on gut microbiome and dietary fiber",
        abstract=f"Abstract {n}: fiber changes microbial diversity in the gut.",
        uid=f"pubmed:{n}",
    )


def _profile() -> Profile:
    return Profile(
        lab_id="test-lab",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=[
            ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                        text="Does dietary fiber change gut microbiome diversity?"),
            ProfileItem(id="asm_1", kind=ProfileItemKind.ASSUMPTION,
                        text="Fiber-derived short chain fatty acids shape the microbiome."),
        ],
    )


def test_classify_paper_returns_valid_classification(monkeypatch) -> None:
    """The full embed->retrieve->prompt->classify chain yields a schema-valid result.

    Retrieval is stubbed (no Redis); the degraded llm.classify runs for real.
    """
    profile = _profile()
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    result = engine.classify_paper(_paper(1), profile)

    assert isinstance(result, Classification)
    assert isinstance(result.label, Label)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.reason, str) and result.reason


def test_active_search_caps_filters_and_sorts(monkeypatch) -> None:
    """active_search drops NOT_RELEVANT, sorts by confidence desc, caps at 5."""
    profile = _profile()
    # 8 staged papers feed the fetch step.
    papers = [_paper(n) for n in range(8)]
    monkeypatch.setattr(engine, "active_search", engine.active_search)  # explicit
    monkeypatch.setattr("app.ingest.fetch_recent", lambda *a, **k: papers)
    monkeypatch.setattr(engine.memory, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    # Deterministic labels keyed by source_id:
    #  - papers 0,1 -> NOT_RELEVANT (must be dropped)
    #  - the rest -> relevant with descending confidence by index
    def fake_classify(system, user, settings=None):
        # Recover the paper index from the rendered title in the user prompt.
        idx = next(n for n in range(8) if f"Paper {n} on" in user)
        if idx < 2:
            return Classification(label=Label.NOT_RELEVANT, reason="nope",
                                  matched_item_id=None, confidence=0.1)
        return Classification(label=Label.ANSWERS, reason=f"hit {idx}",
                              matched_item_id="oq_1", confidence=0.9 - idx * 0.05)

    monkeypatch.setattr(engine.llm, "classify", fake_classify)

    hits = engine.active_search("does fiber change diversity?")

    assert len(hits) <= 5
    assert all(h.classification.label is not Label.NOT_RELEVANT for h in hits)
    confidences = [h.classification.confidence for h in hits]
    assert confidences == sorted(confidences, reverse=True)
    # 6 relevant papers (idx 2..7) but capped at 5; top hit is idx 2 (highest conf).
    assert len(hits) == 5
    assert hits[0].classification.confidence == pytest.approx(0.9 - 2 * 0.05)


def test_run_digest_keeps_only_relevant(monkeypatch) -> None:
    """run_digest classifies each paper and keeps non-NOT_RELEVANT hits."""
    profile = _profile()
    papers = [_paper(n) for n in range(4)]
    monkeypatch.setattr(engine.memory, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    def fake_classify(system, user, settings=None):
        idx = next(n for n in range(4) if f"Paper {n} on" in user)
        if idx % 2 == 0:
            return Classification(label=Label.NOT_RELEVANT, reason="nope",
                                  matched_item_id=None, confidence=0.1)
        return Classification(label=Label.EXTENDS, reason=f"hit {idx}",
                              matched_item_id="asm_1", confidence=0.8)

    monkeypatch.setattr(engine.llm, "classify", fake_classify)

    hits = engine.run_digest("2026-06-21", papers)

    assert len(hits) == 2  # idx 1 and 3
    assert all(h.classification.label is Label.EXTENDS for h in hits)
