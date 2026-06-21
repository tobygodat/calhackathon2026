"""Unit tests for the classification engine (app/engine.py).

engine.py uses lazy imports from sibling modules, so we patch at the SOURCE:
  - app.embeddings.embed_text   (engine does: from .embeddings import embed_text)
  - app.llm.classify            (engine does: from .llm import classify)
  - app.memory.retrieve_relevant
  - app.prompts.build_prompt
  - app.memory.load_profile
  - app.ingest.fetch_recent
  - app.engine.classify_paper   (module-level fn, safe to patch from callers)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.engine import active_search, classify_paper, run_digest
from app.models import Classification, Label, PaperOut, Profile, SearchHit


def _mock_cl(label: Label = Label.ANSWERS, confidence: float = 0.85) -> Classification:
    return Classification(
        label=label,
        reason="Mocked reason.",
        matched_item_id="oq_1",
        confidence=confidence,
    )


def _papers(n: int) -> list[PaperOut]:
    return [
        PaperOut(source="pubmed", source_id=str(i), title=f"Paper {i}",
                 abstract=f"Abstract for paper {i}.")
        for i in range(n)
    ]


class TestClassifyPaper:
    def test_returns_classification(self, sample_paper, sample_profile, settings):
        with patch("app.embeddings.embed_text", return_value=[0.1] * 1536):
            with patch("app.memory.retrieve_relevant",
                       return_value=sample_profile.items):
                with patch("app.prompts.build_prompt",
                           return_value=("system", "user")):
                    with patch("app.llm.classify",
                               return_value=_mock_cl()):
                        result = classify_paper(sample_paper, sample_profile,
                                                settings=settings)
        assert isinstance(result, Classification)
        assert result.label == Label.ANSWERS

    def test_uses_abstract_for_retrieval(self, sample_paper, sample_profile, settings):
        """The engine no longer embeds locally; it passes the paper's abstract
        to retrieve_relevant so the most relevant profile items are selected."""
        captured = []

        def cap_retrieve(query, k=None, settings=None):
            captured.append(query)
            return sample_profile.items

        with patch("app.memory.retrieve_relevant", side_effect=cap_retrieve):
            with patch("app.prompts.build_prompt",
                       return_value=("s", "u")):
                with patch("app.llm.classify",
                           return_value=_mock_cl()):
                    classify_paper(sample_paper, sample_profile,
                                   settings=settings)
        # retrieve_relevant should have been called with the abstract
        assert any(sample_paper.abstract in q for q in captured)

    def test_no_abstract_skips_embed_uses_title_for_retrieve(
        self, sample_paper_no_abstract, sample_profile, settings
    ):
        """When abstract is empty: embed_text is skipped; title is passed to
        retrieve_relevant."""
        captured_retrieve = []

        def cap_retrieve(query, k=None, settings=None):
            captured_retrieve.append(query)
            return sample_profile.items

        with patch("app.embeddings.embed_text") as mock_embed:
            with patch("app.memory.retrieve_relevant", side_effect=cap_retrieve):
                with patch("app.prompts.build_prompt", return_value=("s", "u")):
                    with patch("app.llm.classify", return_value=_mock_cl()):
                        result = classify_paper(sample_paper_no_abstract,
                                                sample_profile, settings=settings)
        assert isinstance(result, Classification)
        mock_embed.assert_not_called()
        assert any(sample_paper_no_abstract.title in q for q in captured_retrieve)

    def test_retrieve_empty_passes_empty_to_build_prompt(
        self, sample_paper, sample_profile, settings
    ):
        """When retrieve_relevant returns [], an empty list reaches build_prompt
        (the engine does not silently substitute all profile items)."""
        captured_items = []

        def capture(items, paper):
            captured_items.append(list(items))
            return "s", "u"

        with patch("app.embeddings.embed_text", return_value=[0.0] * 1536):
            with patch("app.memory.retrieve_relevant", return_value=[]):
                with patch("app.prompts.build_prompt", side_effect=capture):
                    with patch("app.llm.classify", return_value=_mock_cl()):
                        classify_paper(sample_paper, sample_profile,
                                       settings=settings)
        assert captured_items == [[]]

    def test_classification_error_propagates(
        self, sample_paper, sample_profile, settings
    ):
        with patch("app.embeddings.embed_text", return_value=[0.0] * 1536):
            with patch("app.memory.retrieve_relevant",
                       return_value=sample_profile.items):
                with patch("app.prompts.build_prompt", return_value=("s", "u")):
                    with patch("app.llm.classify",
                               side_effect=ValueError("bad json")):
                        with pytest.raises(ValueError):
                            classify_paper(sample_paper, sample_profile,
                                           settings=settings)


class TestActiveSearch:
    def test_returns_list_of_search_hits(self, settings):
        cl = _mock_cl(Label.ANSWERS, 0.9)
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=_papers(3)):
                with patch("app.engine.classify_paper", return_value=cl):
                    result = active_search("fiber", settings=settings)
        assert isinstance(result, list)
        assert all(isinstance(h, SearchHit) for h in result)

    def test_filters_not_relevant(self, settings):
        papers = _papers(4)
        # Map classification by paper id: concurrent classification runs out of
        # order, so a shared counter would race under the thread pool.
        by_id = {
            "0": _mock_cl(Label.ANSWERS, 0.9),
            "1": _mock_cl(Label.NOT_RELEVANT, 0.1),
            "2": _mock_cl(Label.EXTENDS, 0.7),
            "3": _mock_cl(Label.NOT_RELEVANT, 0.05),
        }

        def side(paper, profile, settings=None):
            return by_id[paper.source_id]

        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=papers):
                with patch("app.engine.classify_paper", side_effect=side):
                    result = active_search("query", settings=settings)
        labels = [h.classification.label for h in result]
        assert Label.NOT_RELEVANT not in labels
        assert len(result) == 2

    def test_capped_at_active_search_cap(self, settings):
        cl = _mock_cl(Label.ANSWERS, 0.9)
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=_papers(20)):
                with patch("app.engine.classify_paper", return_value=cl):
                    result = active_search("query", settings=settings)
        assert len(result) <= settings.active_search_cap

    def test_sorted_by_confidence_descending(self, settings):
        papers = _papers(3)
        conf_by_id = {"0": 0.6, "1": 0.95, "2": 0.75}

        def side(paper, profile, settings=None):
            return _mock_cl(Label.ANSWERS, conf_by_id[paper.source_id])

        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=papers):
                with patch("app.engine.classify_paper", side_effect=side):
                    result = active_search("query", settings=settings)
        confs = [h.classification.confidence for h in result]
        assert confs == sorted(confs, reverse=True)
        assert confs == [0.95, 0.75, 0.6]

    def test_empty_papers_returns_empty(self, settings):
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=[]):
                result = active_search("query", settings=settings)
        assert result == []


class TestRunDigest:
    def test_returns_list_of_search_hits(self, settings, sample_paper):
        cl = _mock_cl(Label.ANSWERS, 0.85)
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.engine.classify_paper", return_value=cl):
                result = run_digest("2024-03-15", [sample_paper],
                                    settings=settings)
        assert len(result) == 1
        assert result[0].paper.title == sample_paper.title

    def test_filters_not_relevant(self, settings):
        papers = _papers(2)
        by_id = {"0": _mock_cl(Label.ANSWERS, 0.8),
                 "1": _mock_cl(Label.NOT_RELEVANT, 0.1)}

        def side(paper, profile, settings=None):
            return by_id[paper.source_id]

        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.engine.classify_paper", side_effect=side):
                result = run_digest("2024-03-15", papers, settings=settings)
        assert len(result) == 1
        assert result[0].paper.source_id == "0"

    def test_empty_papers_list(self, settings):
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            result = run_digest("2024-03-15", [], settings=settings)
        assert result == []

    def test_all_relevant_returned_without_cap(self, settings):
        """run_digest has no cap (unlike active_search)."""
        papers = _papers(10)
        cl = _mock_cl(Label.EXTENDS, 0.7)
        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.engine.classify_paper", return_value=cl):
                result = run_digest("2024-03-15", papers, settings=settings)
        assert len(result) == 10


class TestBoundedConcurrency:
    """Classification fans out concurrently but never exceeds the configured
    limit (ARCHITECTURE_DECISIONS.md #12)."""

    def test_run_digest_classifies_concurrently_up_to_limit(self):
        import threading
        import time as _time

        limit = 3
        n = 9
        settings = Settings(anthropic_api_key=None, classify_concurrency=limit)
        papers = _papers(n)

        lock = threading.Lock()
        active = [0]
        peak = [0]

        def slow(paper, profile, settings=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            _time.sleep(0.05)  # hold the slot so overlap is observable
            with lock:
                active[0] -= 1
            return _mock_cl(Label.EXTENDS, 0.7)

        with patch("app.memory.load_profile", return_value=MagicMock(items=[])):
            with patch("app.engine.classify_paper", side_effect=slow):
                result = run_digest("2024-03-15", papers, settings=settings)

        assert len(result) == n        # every paper classified
        # Saturates the limit (proves real concurrency) and never exceeds it.
        assert peak[0] == limit

    def test_concurrency_limit_one_is_serial(self):
        """A limit of 1 degrades to fully serial classification (peak == 1)."""
        import threading
        import time as _time

        settings = Settings(anthropic_api_key=None, classify_concurrency=1)
        papers = _papers(5)
        lock = threading.Lock()
        active = [0]
        peak = [0]

        def slow(paper, profile, settings=None):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            _time.sleep(0.02)
            with lock:
                active[0] -= 1
            return _mock_cl(Label.EXTENDS, 0.7)

        with patch("app.memory.load_profile", return_value=MagicMock(items=[])):
            with patch("app.engine.classify_paper", side_effect=slow):
                run_digest("2024-03-15", papers, settings=settings)

        assert peak[0] == 1


class TestPreFilter:
    """active_search caps LLM work to the pre-filter set regardless of fetch size
    (ARCHITECTURE_DECISIONS.md #12)."""

    def test_active_search_caps_llm_calls_to_preclassify_cap(self):
        import threading

        cap = 7
        fetched = 50
        settings = Settings(anthropic_api_key=None, preclassify_cap=cap,
                            active_search_cap=5)
        papers = _papers(fetched)

        call_lock = threading.Lock()
        calls = [0]

        def counting(paper, profile, settings=None):
            with call_lock:
                calls[0] += 1
            return _mock_cl(Label.ANSWERS, 0.9)

        with patch("app.memory.load_profile", return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=papers):
                with patch("app.engine.classify_paper", side_effect=counting):
                    result = active_search("fiber", settings=settings)

        # The LLM ran on exactly the pre-filter set, never the full fetch.
        assert calls[0] == cap
        assert calls[0] < fetched
        assert len(result) <= settings.active_search_cap

    def test_active_search_no_prefilter_when_under_cap(self):
        """When fetch <= cap, every fetched paper is classified (no trimming)."""
        settings = Settings(anthropic_api_key=None, preclassify_cap=20,
                            active_search_cap=50)
        papers = _papers(4)
        calls = [0]

        def counting(paper, profile, settings=None):
            calls[0] += 1
            return _mock_cl(Label.ANSWERS, 0.9)

        with patch("app.memory.load_profile", return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=papers):
                with patch("app.engine.classify_paper", side_effect=counting):
                    active_search("fiber", settings=settings)
        assert calls[0] == 4

    def test_prefilter_keeps_most_relevant_by_lexical_signal(self, settings):
        from app.engine import _prefilter

        papers = [
            PaperOut(source="s", source_id="a", title="cardiac surgery outcomes",
                     abstract="heart valve replacement techniques"),
            PaperOut(source="s", source_id="b", title="gut microbiome fiber study",
                     abstract="dietary fiber shapes the gut microbiome and butyrate"),
            PaperOut(source="s", source_id="c", title="quantum optics",
                     abstract="photon entanglement experiment"),
        ]
        # Force the lexical fallback for a deterministic ranking.
        with patch("app.engine._vector_scores", return_value=None):
            top = _prefilter("gut microbiome fiber", papers, cap=1, settings=settings)
        assert len(top) == 1
        assert top[0].source_id == "b"
