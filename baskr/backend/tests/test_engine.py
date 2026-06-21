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


def test_active_search_sorts_by_label_priority(monkeypatch) -> None:
    """active_search surfaces all four sorts ordered CONTRADICTS->VERIFIES->EXTENDS
    ->TANGENTIAL (confidence desc within each); a high-confidence TANGENTIAL still
    sorts last."""
    profile = _profile()
    papers = [_paper(n) for n in range(5)]
    monkeypatch.setattr("app.ingest.fetch_recent", lambda *a, **k: papers)
    monkeypatch.setattr(engine.memory, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    labels = {
        0: (Label.TANGENTIAL, 0.95),   # highest confidence, lowest priority
        1: (Label.CONTRADICTS, 0.40),
        2: (Label.VERIFIES, 0.90),
        3: (Label.EXTENDS, 0.70),
        4: (Label.VERIFIES, 0.60),
    }

    def fake_classify(system, user, settings=None):
        idx = next(n for n in range(5) if f"Paper {n} on" in user)
        label, conf = labels[idx]
        return Classification(label=label, reason=f"hit {idx}",
                              matched_item_id=None, confidence=conf)

    monkeypatch.setattr(engine.llm, "classify", fake_classify)

    hits = engine.active_search("does fiber change diversity?")

    assert [h.classification.label for h in hits] == [
        Label.CONTRADICTS, Label.VERIFIES, Label.VERIFIES, Label.EXTENDS,
        Label.TANGENTIAL,
    ]
    # within VERIFIES, higher confidence first
    assert hits[1].classification.confidence == pytest.approx(0.90)
    assert hits[2].classification.confidence == pytest.approx(0.60)
    # the 0.95-confidence TANGENTIAL is surfaced last, below the 0.40 CONTRADICTS
    assert hits[-1].classification.label is Label.TANGENTIAL


def test_active_search_caps_at_active_search_cap(monkeypatch) -> None:
    """active_search caps the sorted result at settings.active_search_cap."""
    profile = _profile()
    papers = [_paper(n) for n in range(8)]
    monkeypatch.setattr("app.ingest.fetch_recent", lambda *a, **k: papers)
    monkeypatch.setattr(engine.memory, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    def fake_classify(system, user, settings=None):
        idx = next(n for n in range(8) if f"Paper {n} on" in user)
        return Classification(label=Label.VERIFIES, reason=f"hit {idx}",
                              matched_item_id="oq_1", confidence=0.9 - idx * 0.05)

    monkeypatch.setattr(engine.llm, "classify", fake_classify)

    hits = engine.active_search("q")

    assert len(hits) == 5  # active_search_cap
    confidences = [h.classification.confidence for h in hits]
    assert confidences == sorted(confidences, reverse=True)


def test_run_digest_surfaces_all_four_sorted(monkeypatch) -> None:
    """run_digest keeps ALL papers (incl TANGENTIAL) sorted by label priority."""
    profile = _profile()
    papers = [_paper(n) for n in range(4)]
    monkeypatch.setattr(engine.memory, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(engine.memory, "retrieve_relevant",
                        lambda *a, **k: profile.items)

    labels = {
        0: Label.TANGENTIAL,
        1: Label.EXTENDS,
        2: Label.CONTRADICTS,
        3: Label.VERIFIES,
    }

    def fake_classify(system, user, settings=None):
        idx = next(n for n in range(4) if f"Paper {n} on" in user)
        return Classification(label=labels[idx], reason=f"hit {idx}",
                              matched_item_id=None, confidence=0.8)

    monkeypatch.setattr(engine.llm, "classify", fake_classify)

    hits = engine.run_digest("2026-06-21", papers)

    assert len(hits) == 4  # nothing dropped — all four sorts surfaced
    assert [h.classification.label for h in hits] == [
        Label.CONTRADICTS, Label.VERIFIES, Label.EXTENDS, Label.TANGENTIAL,
    ]


def test_retrieve_prior_work_uses_corpus_filters_self_and_caps(monkeypatch) -> None:
    """_retrieve_prior_work pulls from the vector corpus (query_similar), drops the
    paper itself, and caps at corpus_top_k."""
    from app.config import SETTINGS

    paper = _paper(1)  # uid "pubmed:1"
    records = [
        {"uid": "pubmed:1", "title": "the paper itself"},  # must be filtered out
        {"uid": "pubmed:99", "title": "neighbour A"},
        {"uid": "pubmed:98", "title": "neighbour B"},
        {"uid": "pubmed:97", "title": "neighbour C"},
        {"uid": "pubmed:96", "title": "neighbour D"},
        {"uid": "pubmed:95", "title": "neighbour E"},
        {"uid": "pubmed:94", "title": "neighbour F"},
    ]
    monkeypatch.setattr("app.redis_client.query_similar", lambda *a, **k: records)

    prior = engine._retrieve_prior_work([0.1] * 4, paper, SETTINGS)

    assert all(p["uid"] != "pubmed:1" for p in prior)   # self filtered
    assert len(prior) == SETTINGS.corpus_top_k          # capped
    assert prior[0]["title"] == "neighbour A"


def test_retrieve_prior_work_degrades_when_corpus_unavailable(monkeypatch) -> None:
    """If the corpus/Redis raises, prior-work retrieval returns [] (offline-safe)."""
    from app.config import SETTINGS

    def boom(*a, **k):
        raise ConnectionError("no redis")

    monkeypatch.setattr("app.redis_client.query_similar", boom)
    assert engine._retrieve_prior_work([0.1] * 4, _paper(1), SETTINGS) == []
