"""Unit tests for the OpenAlex source (all HTTP mocked)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ..config import Config
from ..models import Paper
from ..sources.openalex import OpenAlexSource


def _mock_response(json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _full_work():
    return {
        "id": "https://openalex.org/W123",
        "title": "A Study of Things",
        "display_name": "A Study of Things",
        "doi": "https://doi.org/10.1234/ABC.xyz",
        "publication_date": "2026-06-15",
        "abstract_inverted_index": {
            "Hello": [0],
            "world": [1],
            "again": [2],
        },
        "authorships": [
            {"author": {"display_name": "Jane Doe"}},
            {"author": {"display_name": "John Smith"}},
        ],
        "primary_location": {
            "source": {"display_name": "Journal of Things"},
            "landing_page_url": "https://example.com/landing",
        },
        "concepts": [
            {"display_name": "Biology"},
            {"display_name": "Genetics"},
        ],
    }


class ReconstructAbstractTests(unittest.TestCase):
    def setUp(self):
        self.src = OpenAlexSource(Config())

    def test_rebuilds_word_order(self):
        inv = {"quick": [1], "The": [0], "fox": [2]}
        self.assertEqual(self.src._reconstruct_abstract(inv), "The quick fox")

    def test_handles_repeated_words(self):
        inv = {"the": [0, 2], "cat": [1, 3]}
        self.assertEqual(self.src._reconstruct_abstract(inv), "the cat the cat")

    def test_none_returns_empty(self):
        self.assertEqual(self.src._reconstruct_abstract(None), "")

    def test_empty_returns_empty(self):
        self.assertEqual(self.src._reconstruct_abstract({}), "")


class ParseItemTests(unittest.TestCase):
    def setUp(self):
        self.src = OpenAlexSource(Config())

    def test_full_work_mapping(self):
        p = self.src._parse_item(_full_work())
        self.assertIsInstance(p, Paper)
        self.assertEqual(p.source, "openalex")
        self.assertEqual(p.source_id, "W123")
        self.assertEqual(p.title, "A Study of Things")
        # bare, lowercased doi
        self.assertEqual(p.doi, "10.1234/abc.xyz")
        self.assertEqual(p.abstract, "Hello world again")
        self.assertEqual(p.authors, ["Jane Doe", "John Smith"])
        self.assertEqual(p.journal, "Journal of Things")
        self.assertEqual(p.published, "2026-06-15")
        self.assertEqual(p.categories, ["Biology", "Genetics"])
        # url prefers the doi link
        self.assertEqual(p.url, "https://doi.org/10.1234/abc.xyz")
        self.assertEqual(p.raw, {"openalex_id": "https://openalex.org/W123"})

    def test_sparse_work_does_not_raise(self):
        sparse = {
            "id": "https://openalex.org/W999",
            "display_name": "Bare",
            "publication_date": "2026-01-01",
        }
        p = self.src._parse_item(sparse)
        self.assertEqual(p.source, "openalex")
        self.assertEqual(p.source_id, "W999")
        self.assertEqual(p.title, "Bare")
        self.assertIsNone(p.doi)
        self.assertEqual(p.abstract, "")
        self.assertEqual(p.authors, [])
        self.assertIsNone(p.journal)
        self.assertEqual(p.categories, [])
        # no doi, no landing -> falls back to the openalex id
        self.assertEqual(p.url, "https://openalex.org/W999")

    def test_url_falls_back_to_landing_when_no_doi(self):
        work = _full_work()
        work.pop("doi")
        p = self.src._parse_item(work)
        self.assertIsNone(p.doi)
        self.assertEqual(p.url, "https://example.com/landing")

    def test_null_primary_location(self):
        work = _full_work()
        work["primary_location"] = None
        p = self.src._parse_item(work)
        self.assertIsNone(p.journal)


class FetchRecentTests(unittest.TestCase):
    def setUp(self):
        self.src = OpenAlexSource(Config())

    def test_respects_max_results(self):
        items = [
            {"id": f"https://openalex.org/W{i}", "display_name": f"P{i}",
             "publication_date": "2026-06-01"}
            for i in range(20)
        ]
        with patch.object(self.src, "_get",
                          return_value=_mock_response({"results": items, "meta": {}})):
            papers = self.src.fetch_recent("cancer", days=7, max_results=5)
        self.assertLessEqual(len(papers), 5)
        self.assertEqual(len(papers), 5)

    def test_returns_openalex_papers(self):
        with patch.object(self.src, "_get",
                          return_value=_mock_response({"results": [_full_work()], "meta": {}})):
            papers = self.src.fetch_recent("biology", days=30, max_results=10)
        self.assertEqual(len(papers), 1)
        self.assertTrue(all(isinstance(p, Paper) for p in papers))
        self.assertTrue(all(p.source == "openalex" for p in papers))
        self.assertEqual(papers[0].title, "A Study of Things")

    def test_empty_results(self):
        with patch.object(self.src, "_get",
                          return_value=_mock_response({"results": [], "meta": {}})):
            papers = self.src.fetch_recent("nothing", days=7, max_results=5)
        self.assertEqual(papers, [])


class NameTests(unittest.TestCase):
    def test_name_attribute(self):
        self.assertEqual(OpenAlexSource.name, "openalex")
        self.assertEqual(OpenAlexSource(Config()).name, "openalex")


if __name__ == "__main__":
    unittest.main()
