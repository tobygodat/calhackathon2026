"""Unit tests for data_pipeline/pipeline.py.

Tests cover:
- DataPipeline constructor — valid + invalid sources
- DataPipeline.fetch() — parallel and sequential, with mocked sources
- FetchResult dataclass — counts, errors, papers, __len__
- DataPipeline._dedupe() — DOI dedup, fingerprint dedup, abstract-length preference,
  newest-first sort, no double-counting via id() guard
- Source error isolation — one failing source doesn't prevent others returning
"""

import unittest
from unittest.mock import patch, MagicMock

from ..models import Paper
from ..pipeline import DataPipeline, FetchResult
from ..config import Config


def make_paper(
    source="pubmed",
    source_id="1",
    title="Test Paper",
    abstract="",
    doi=None,
    published=None,
) -> Paper:
    return Paper(
        source=source,
        source_id=source_id,
        title=title,
        abstract=abstract,
        doi=doi,
        published=published,
    )


class TestFetchResult(unittest.TestCase):
    def test_len_empty(self):
        r = FetchResult()
        self.assertEqual(len(r), 0)

    def test_len_with_papers(self):
        r = FetchResult(papers=[make_paper(), make_paper(source_id="2")])
        self.assertEqual(len(r), 2)

    def test_defaults(self):
        r = FetchResult()
        self.assertEqual(r.papers, [])
        self.assertEqual(r.errors, {})
        self.assertEqual(r.counts, {})


class TestDataPipelineConstructor(unittest.TestCase):
    def test_default_uses_all_sources(self):
        from ..sources import SOURCE_REGISTRY
        pipe = DataPipeline()
        self.assertEqual(set(pipe.sources.keys()), set(SOURCE_REGISTRY.keys()))

    def test_subset_sources(self):
        pipe = DataPipeline(sources=["pubmed"])
        self.assertIn("pubmed", pipe.sources)
        self.assertNotIn("arxiv", pipe.sources)

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError) as ctx:
            DataPipeline(sources=["nonexistent"])
        self.assertIn("nonexistent", str(ctx.exception))

    def test_unknown_source_message_lists_available(self):
        with self.assertRaises(ValueError) as ctx:
            DataPipeline(sources=["ghost_source"])
        self.assertIn("Available", str(ctx.exception))

    def test_custom_config_stored(self):
        cfg = Config(contact_email="test@test.com")
        pipe = DataPipeline(config=cfg)
        self.assertEqual(pipe.config.contact_email, "test@test.com")


class _MockSource:
    """Minimal mock that behaves like a PaperSource."""
    name = "mock"
    def __init__(self, config, papers=None, raise_exc=None):
        self.config = config
        self._papers = papers or []
        self._raise_exc = raise_exc

    def fetch_recent(self, query, *, days, max_results):
        if self._raise_exc:
            raise self._raise_exc
        return self._papers[:]


class TestDataPipelineFetch(unittest.TestCase):
    def _pipe_with_mock(self, papers=None, raise_exc=None):
        """Return a DataPipeline whose only source is a _MockSource."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = Config()
        mock_src = _MockSource(pipe.config, papers=papers, raise_exc=raise_exc)
        pipe.sources = {"mock": mock_src}
        return pipe

    def test_fetch_returns_papers(self):
        # Use distinct titles so dedupe doesn't collapse them (same title → same fingerprint)
        papers = [
            make_paper(source_id="1", title="Paper Alpha"),
            make_paper(source_id="2", title="Paper Beta"),
        ]
        pipe = self._pipe_with_mock(papers=papers)
        result = pipe.fetch("test query", days=7, max_per_source=50, parallel=False)
        self.assertIsInstance(result, FetchResult)
        self.assertEqual(len(result.papers), 2)

    def test_fetch_counts_recorded(self):
        papers = [make_paper(source_id=str(i)) for i in range(5)]
        pipe = self._pipe_with_mock(papers=papers)
        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertEqual(result.counts["mock"], 5)

    def test_fetch_source_error_isolated(self):
        pipe = self._pipe_with_mock(raise_exc=RuntimeError("network down"))
        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertIn("mock", result.errors)
        self.assertIn("RuntimeError", result.errors["mock"])
        self.assertEqual(result.papers, [])
        self.assertEqual(result.counts["mock"], 0)

    def test_fetch_parallel_produces_same_result(self):
        papers = [make_paper(source_id="1"), make_paper(source_id="2")]
        pipe = self._pipe_with_mock(papers=papers)
        r_seq = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        r_par = pipe.fetch("test", days=7, max_per_source=50, parallel=True)
        # Both should have same papers (possibly reordered but same count)
        self.assertEqual(len(r_seq.papers), len(r_par.papers))

    def test_fetch_uses_config_defaults_when_not_specified(self):
        """When days/max_per_source not passed, fetch still works."""
        papers = [make_paper()]
        pipe = self._pipe_with_mock(papers=papers)
        result = pipe.fetch("test")
        self.assertEqual(len(result.papers), 1)

    def test_fetch_multi_source_accumulates(self):
        """Two sources each returning 2 papers → 4 papers before dedupe."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = Config()
        src_a = _MockSource(pipe.config, papers=[
            make_paper(source="pubmed", source_id="1", title="Alpha"),
            make_paper(source="pubmed", source_id="2", title="Beta"),
        ])
        src_b = _MockSource(pipe.config, papers=[
            make_paper(source="arxiv", source_id="3", title="Gamma"),
            make_paper(source="arxiv", source_id="4", title="Delta"),
        ])
        pipe.sources = {"a": src_a, "b": src_b}
        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertEqual(len(result.papers), 4)


class TestDeduplication(unittest.TestCase):
    def test_same_doi_deduped(self):
        p1 = make_paper(source="pubmed", source_id="1", doi="10.1/abc",
                        abstract="short")
        p2 = make_paper(source="arxiv", source_id="2", doi="10.1/abc",
                        abstract="much longer abstract text here")
        result = DataPipeline._dedupe([p1, p2])
        self.assertEqual(len(result), 1)
        # Winner has the longer abstract
        self.assertEqual(result[0].abstract, "much longer abstract text here")

    def test_same_title_deduped_by_fingerprint(self):
        # Same title (different case) → same fingerprint → dedupe
        p1 = make_paper(source="pubmed", source_id="1", title="Gut Microbiome",
                        abstract="short")
        p2 = make_paper(source="arxiv", source_id="2", title="gut microbiome",
                        abstract="longer abstract wins")
        result = DataPipeline._dedupe([p1, p2])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].abstract, "longer abstract wins")

    def test_different_papers_not_deduped(self):
        p1 = make_paper(source_id="1", title="Paper One", doi="10.1/aaa")
        p2 = make_paper(source_id="2", title="Paper Two", doi="10.1/bbb")
        result = DataPipeline._dedupe([p1, p2])
        self.assertEqual(len(result), 2)

    def test_sorted_newest_first(self):
        p_old = make_paper(source_id="1", title="Old Paper", published="2022-01-01")
        p_new = make_paper(source_id="2", title="New Paper", published="2024-06-01")
        p_mid = make_paper(source_id="3", title="Mid Paper", published="2023-03-15")
        result = DataPipeline._dedupe([p_old, p_mid, p_new])
        dates = [p.published for p in result]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_none_published_sorted_last(self):
        p_dated = make_paper(source_id="1", title="Dated", published="2024-01-01")
        p_none = make_paper(source_id="2", title="Undated", published=None)
        result = DataPipeline._dedupe([p_none, p_dated])
        # Published date sorts by string, None→"" goes last (reverse sort)
        self.assertEqual(result[0].published, "2024-01-01")

    def test_empty_list(self):
        result = DataPipeline._dedupe([])
        self.assertEqual(result, [])

    def test_single_paper(self):
        p = make_paper(source_id="1", title="Solo")
        result = DataPipeline._dedupe([p])
        self.assertEqual(len(result), 1)

    def test_abstract_length_tiebreak(self):
        """Among papers with same uid, keep longest abstract."""
        p_long = make_paper(doi="10.1/x", abstract="a" * 500)
        p_short = make_paper(doi="10.1/x", abstract="b" * 10)
        result = DataPipeline._dedupe([p_long, p_short])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].abstract), 500)

    def test_doi_same_case_insensitive(self):
        """DOI in uid is lowercased, so uppercase/lowercase DOIs should dedup."""
        p1 = make_paper(doi="10.1/ABC", abstract="aaa")
        p2 = make_paper(doi="10.1/abc", abstract="longer abstract here yes")
        result = DataPipeline._dedupe([p1, p2])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
