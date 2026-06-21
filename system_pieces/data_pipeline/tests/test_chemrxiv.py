"""Tests for the ChemRxiv source. All HTTP is mocked; no live calls."""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from ..config import Config
from ..models import Paper
from ..sources.chemrxiv import ChemRxivSource


def _mock_response(json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _full_item(item_id="abc123", published="2026-06-20T12:00:00"):
    return {
        "id": item_id,
        "title": "  A Study of  Catalysis  ",
        "abstract": "We report\na new catalyst.",
        "doi": "https://doi.org/10.26434/CHEMRXIV-2026-XYZ",
        "authors": [
            {"firstName": "Ada", "lastName": "Lovelace"},
            {"firstName": "Alan", "lastName": "Turing"},
        ],
        "publishedDate": published,
        "categories": [
            {"name": "Organic Chemistry"},
            {"name": "Catalysis"},
            {"id": "noname"},  # should be skipped (no name)
        ],
    }


class ParseItemTests(unittest.TestCase):
    def setUp(self):
        self.src = ChemRxivSource(Config())

    def test_parse_full_item(self):
        paper = self.src._parse_item(_full_item())
        self.assertIsInstance(paper, Paper)
        self.assertEqual(paper.source, "chemrxiv")
        self.assertEqual(paper.source_id, "abc123")
        self.assertEqual(paper.title, "A Study of Catalysis")
        self.assertEqual(paper.abstract, "We report a new catalyst.")
        # bare, lowercased doi
        self.assertEqual(paper.doi, "10.26434/chemrxiv-2026-xyz")
        self.assertEqual(paper.authors, ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(paper.journal, "ChemRxiv")
        self.assertEqual(paper.published, "2026-06-20")
        self.assertEqual(paper.categories, ["Organic Chemistry", "Catalysis"])
        self.assertEqual(paper.url, "https://doi.org/10.26434/chemrxiv-2026-xyz")

    def test_parse_sparse_item(self):
        # no doi, no abstract, no authors, no categories
        sparse = {"id": "x1", "title": "Bare Item", "submittedDate": "2026-01-02"}
        paper = self.src._parse_item(sparse)
        self.assertEqual(paper.source_id, "x1")
        self.assertEqual(paper.title, "Bare Item")
        self.assertEqual(paper.abstract, "")
        self.assertEqual(paper.authors, [])
        self.assertIsNone(paper.doi)
        self.assertIsNone(paper.url)
        self.assertEqual(paper.categories, [])
        self.assertEqual(paper.published, "2026-01-02")

    def test_parse_empty_item(self):
        paper = self.src._parse_item({})
        self.assertEqual(paper.source, "chemrxiv")
        self.assertEqual(paper.source_id, "")
        self.assertIsNone(paper.doi)

    def test_extract_item_nested(self):
        inner = {"id": "z"}
        self.assertEqual(ChemRxivSource._extract_item({"item": inner}), inner)

    def test_extract_item_bare(self):
        bare = {"id": "z", "title": "t"}
        self.assertEqual(ChemRxivSource._extract_item(bare), bare)

    def test_extract_item_non_dict(self):
        self.assertEqual(ChemRxivSource._extract_item("nope"), {})


class FetchRecentTests(unittest.TestCase):
    def setUp(self):
        self.src = ChemRxivSource(Config())

    def test_name_attribute(self):
        self.assertEqual(ChemRxivSource.name, "chemrxiv")
        self.assertEqual(self.src.name, "chemrxiv")

    def test_date_filtering(self):
        recent = date.today().strftime("%Y-%m-%d") + "T08:00:00"
        old = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d") + "T08:00:00"
        payload = {
            "totalCount": 2,
            "itemHits": [
                {"item": _full_item(item_id="recent", published=recent)},
                {"item": _full_item(item_id="old", published=old)},
            ],
        }
        with patch.object(self.src, "_get", return_value=_mock_response(payload)):
            papers = self.src.fetch_recent("catalysis", days=7, max_results=10)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source_id, "recent")

    def test_max_results_respected(self):
        today = date.today().strftime("%Y-%m-%d") + "T08:00:00"
        hits = [
            {"item": _full_item(item_id=f"id{i}", published=today)}
            for i in range(20)
        ]
        payload = {"totalCount": 20, "itemHits": hits}
        with patch.object(self.src, "_get", return_value=_mock_response(payload)):
            papers = self.src.fetch_recent("catalysis", days=7, max_results=5)
        self.assertLessEqual(len(papers), 5)

    def test_fetch_returns_chemrxiv_papers(self):
        today = date.today().strftime("%Y-%m-%d") + "T08:00:00"
        payload = {
            "totalCount": 1,
            "itemHits": [{"item": _full_item(published=today)}],
        }
        with patch.object(self.src, "_get", return_value=_mock_response(payload)):
            papers = self.src.fetch_recent("catalysis", days=7, max_results=10)
        self.assertTrue(papers)
        for p in papers:
            self.assertEqual(p.source, "chemrxiv")
            self.assertIsInstance(p, Paper)

    def test_fetch_empty_payload(self):
        with patch.object(self.src, "_get", return_value=_mock_response({})):
            papers = self.src.fetch_recent("catalysis", days=7, max_results=10)
        self.assertEqual(papers, [])


if __name__ == "__main__":
    unittest.main()
