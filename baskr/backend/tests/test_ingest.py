"""Unit tests for the paper ingest module (app/ingest.py).

ingest.py imports DataPipeline lazily from system_pieces.data_pipeline.
Since conftest.py adds calhackathon2026 to sys.path, the real module is
importable. We patch system_pieces.data_pipeline.DataPipeline to avoid
actual network calls.

For embed_batch and upsert_paper we patch at their SOURCE modules
(app.embeddings.embed_batch, app.redis_client.upsert_paper).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.ingest import fetch_recent, ingest
from app.models import PaperOut


def _make_pipeline_paper(
    source: str = "pubmed",
    source_id: str = "1",
    title: str = "Test Paper",
    abstract: str = "Test abstract.",
    doi: str | None = None,
) -> MagicMock:
    """Return a mock that behaves like a data_pipeline.Paper."""
    p = MagicMock()
    p.source = source
    p.source_id = source_id
    p.title = title
    p.abstract = abstract
    p.authors = ["Author A"]
    p.doi = doi
    p.url = None
    p.journal = None
    p.published = "2024-03-15"
    p.categories = []
    p.uid = f"doi:{doi}" if doi else f"{source}:{source_id}"
    return p


def _make_fetch_result(papers: list) -> MagicMock:
    r = MagicMock()
    r.papers = papers
    r.errors = {}
    r.counts = {(p.source if hasattr(p, "source") else "mock"): 1 for p in papers}
    return r


class TestFetchRecent:
    def test_returns_list_of_paper_out(self, settings):
        pipeline_papers = [_make_pipeline_paper(source_id="1")]
        mock_result = _make_fetch_result(pipeline_papers)

        with patch("system_pieces.data_pipeline.DataPipeline") as MockPipeline:
            MockPipeline.return_value.fetch.return_value = mock_result
            result = fetch_recent("gut microbiome", days=7, settings=settings)

        assert isinstance(result, list)
        assert all(isinstance(p, PaperOut) for p in result)

    def test_returns_correct_count(self, settings):
        pipeline_papers = [_make_pipeline_paper(source_id=str(i)) for i in range(5)]
        mock_result = _make_fetch_result(pipeline_papers)

        with patch("system_pieces.data_pipeline.DataPipeline") as MockPipeline:
            MockPipeline.return_value.fetch.return_value = mock_result
            result = fetch_recent("query", days=7, settings=settings)

        assert len(result) == 5

    def test_paper_fields_mapped_correctly(self, settings):
        p = _make_pipeline_paper(
            source="arxiv",
            source_id="2401.12345",
            title="Fiber and Microbiome",
            abstract="We studied fiber.",
            doi="10.1234/fiber",
        )
        mock_result = _make_fetch_result([p])

        with patch("system_pieces.data_pipeline.DataPipeline") as MockPipeline:
            MockPipeline.return_value.fetch.return_value = mock_result
            result = fetch_recent("fiber", days=7, settings=settings)

        out = result[0]
        assert out.source == "arxiv"
        assert out.source_id == "2401.12345"
        assert out.title == "Fiber and Microbiome"
        assert out.abstract == "We studied fiber."
        assert out.doi == "10.1234/fiber"

    def test_empty_results(self, settings):
        mock_result = _make_fetch_result([])

        with patch("system_pieces.data_pipeline.DataPipeline") as MockPipeline:
            MockPipeline.return_value.fetch.return_value = mock_result
            result = fetch_recent("obscure query", days=7, settings=settings)

        assert result == []

    def test_passes_days_to_pipeline(self, settings):
        mock_result = _make_fetch_result([])

        with patch("system_pieces.data_pipeline.DataPipeline") as MockPipeline:
            MockPipeline.return_value.fetch.return_value = mock_result
            fetch_recent("microbiome fiber", days=14, settings=settings)

        call_kwargs = MockPipeline.return_value.fetch.call_args
        # days=14 should appear in the call
        all_args = str(call_kwargs)
        assert "14" in all_args


class TestIngest:
    def test_returns_count_of_embedded_papers(self, settings):
        papers_out = [
            PaperOut(source="pubmed", source_id="1", title="P1",
                     abstract="Abstract 1."),
            PaperOut(source="pubmed", source_id="2", title="P2",
                     abstract="Abstract 2."),
        ]
        fake_embs = [[0.1] * 1536, [0.2] * 1536]

        with patch("app.ingest.fetch_recent", return_value=papers_out):
            with patch("app.embeddings.embed_batch", return_value=fake_embs):
                with patch("app.redis_client.upsert_paper") as mock_upsert:
                    count = ingest("query", days=7, settings=settings)

        assert count == 2
        assert mock_upsert.call_count == 2

    def test_skips_papers_without_abstract(self, settings):
        papers_out = [
            PaperOut(source="pubmed", source_id="1", title="Has Abstract",
                     abstract="Some abstract."),
            PaperOut(source="pubmed", source_id="2", title="No Abstract",
                     abstract=""),
        ]
        fake_embs = [[0.1] * 1536]

        with patch("app.ingest.fetch_recent", return_value=papers_out):
            with patch("app.embeddings.embed_batch", return_value=fake_embs):
                with patch("app.redis_client.upsert_paper") as mock_upsert:
                    count = ingest("query", days=7, settings=settings)

        assert count == 1
        assert mock_upsert.call_count == 1

    def test_returns_zero_when_no_papers(self, settings):
        with patch("app.ingest.fetch_recent", return_value=[]):
            with patch("app.embeddings.embed_batch", return_value=[]):
                with patch("app.redis_client.upsert_paper") as mock_upsert:
                    count = ingest("query", days=7, settings=settings)

        assert count == 0
        mock_upsert.assert_not_called()

    def test_embed_batch_called_with_abstracts(self, settings):
        papers_out = [
            PaperOut(source="pubmed", source_id="1", title="P1",
                     abstract="Abstract A."),
            PaperOut(source="pubmed", source_id="2", title="P2",
                     abstract="Abstract B."),
        ]
        fake_embs = [[0.1] * 1536, [0.2] * 1536]

        with patch("app.ingest.fetch_recent", return_value=papers_out):
            with patch("app.embeddings.embed_batch",
                       return_value=fake_embs) as mock_embed:
                with patch("app.redis_client.upsert_paper"):
                    ingest("query", days=7, settings=settings)

        texts_passed = mock_embed.call_args[0][0]
        assert "Abstract A." in texts_passed
        assert "Abstract B." in texts_passed
