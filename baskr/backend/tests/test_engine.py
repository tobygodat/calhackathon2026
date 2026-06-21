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

    def test_uses_abstract_for_embedding(self, sample_paper, sample_profile, settings):
        captured = []
        with patch("app.embeddings.embed_text",
                   side_effect=lambda t, settings=None: captured.append(t) or [0.0] * 1536):
            with patch("app.memory.retrieve_relevant",
                       return_value=sample_profile.items):
                with patch("app.prompts.build_prompt",
                           return_value=("s", "u")):
                    with patch("app.llm.classify",
                               return_value=_mock_cl()):
                        classify_paper(sample_paper, sample_profile,
                                       settings=settings)
        # embed_text should have been called with the abstract
        assert any(sample_paper.abstract in t for t in captured)

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
        classifications = [
            _mock_cl(Label.ANSWERS, 0.9),
            _mock_cl(Label.NOT_RELEVANT, 0.1),
            _mock_cl(Label.EXTENDS, 0.7),
            _mock_cl(Label.NOT_RELEVANT, 0.05),
        ]
        counter = [0]

        def side(paper, profile, settings=None):
            idx = counter[0]
            counter[0] += 1
            return classifications[idx]

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
        confidences = [0.6, 0.95, 0.75]
        counter = [0]

        def side(paper, profile, settings=None):
            idx = counter[0]
            counter[0] += 1
            return _mock_cl(Label.ANSWERS, confidences[idx])

        with patch("app.memory.load_profile",
                   return_value=MagicMock(items=[])):
            with patch("app.ingest.fetch_recent", return_value=papers):
                with patch("app.engine.classify_paper", side_effect=side):
                    result = active_search("query", settings=settings)
        confs = [h.classification.confidence for h in result]
        assert confs == sorted(confs, reverse=True)

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
        cls = [_mock_cl(Label.ANSWERS, 0.8), _mock_cl(Label.NOT_RELEVANT, 0.1)]
        counter = [0]

        def side(paper, profile, settings=None):
            idx = counter[0]; counter[0] += 1
            return cls[idx]

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
