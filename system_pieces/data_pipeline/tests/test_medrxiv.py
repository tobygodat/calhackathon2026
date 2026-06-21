"""Tests for MedRxivSource — the medRxiv server of the shared bioRxiv details API."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ..config import Config
from ..models import Paper
from ..sources.medrxiv import MedRxivSource


def _mock_response(json_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


class TestMedRxivSource(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.src = MedRxivSource(self.cfg)

    def _make_item(self, **kwargs) -> dict:
        return {
            "doi": kwargs.get("doi", "10.1101/2024.01.01.000001"),
            "title": kwargs.get("title", "A medRxiv Preprint"),
            "abstract": kwargs.get("abstract", "Some abstract content."),
            "authors": kwargs.get("authors", "Smith J; Doe A"),
            "date": kwargs.get("date", "2024-06-01"),
            "category": kwargs.get("category", "epidemiology"),
            "version": kwargs.get("version", "1"),
        }

    # --- identity / server wiring ---

    def test_name_is_medrxiv(self):
        self.assertEqual(MedRxivSource.name, "medrxiv")
        self.assertEqual(self.src.name, "medrxiv")

    def test_server_is_medrxiv(self):
        self.assertEqual(self.src.server, "medrxiv")

    def test_constructs_without_config(self):
        src = MedRxivSource()
        self.assertEqual(src.server, "medrxiv")
        self.assertEqual(src.name, "medrxiv")

    # --- _parse_item ---

    def test_parse_item_full(self):
        item = self._make_item(
            doi="10.1101/2024.05.05.000099",
            title="Vaccine Efficacy Study",
            abstract="A randomized trial.",
            authors="Alpha A; Beta B; Gamma C",
            date="2024-05-05",
            category="infectious diseases",
        )
        paper = self.src._parse_item(item)
        self.assertIsInstance(paper, Paper)
        self.assertEqual(paper.source, "medrxiv")
        self.assertEqual(paper.journal, "medrxiv")
        self.assertEqual(paper.doi, "10.1101/2024.05.05.000099")
        self.assertEqual(paper.title, "Vaccine Efficacy Study")
        self.assertEqual(paper.abstract, "A randomized trial.")
        self.assertEqual(paper.authors, ["Alpha A", "Beta B", "Gamma C"])
        self.assertEqual(paper.url, "https://doi.org/10.1101/2024.05.05.000099")
        self.assertEqual(str(paper.published), "2024-05-05")
        self.assertIn("infectious diseases", paper.categories)

    def test_parse_item_authors_split_on_semicolon(self):
        item = self._make_item(authors="Smith J; Doe A; Lee K")
        paper = self.src._parse_item(item)
        self.assertEqual(paper.authors, ["Smith J", "Doe A", "Lee K"])

    def test_parse_item_bare_doi_and_url(self):
        item = self._make_item(doi="10.1101/abc.123")
        paper = self.src._parse_item(item)
        self.assertEqual(paper.doi, "10.1101/abc.123")
        self.assertEqual(paper.url, "https://doi.org/10.1101/abc.123")

    # --- URL targets the medrxiv server ---

    def test_built_url_targets_medrxiv_server(self):
        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            return _mock_response(json_data={"collection": [self._make_item()]})

        with patch.object(self.src, "_get", side_effect=fake_get):
            self.src.fetch_recent("", days=7, max_results=5)

        self.assertIn("url", captured)
        self.assertIn("/medrxiv/", captured["url"])

    # --- fetch_recent ---

    def test_fetch_recent_sets_source_medrxiv(self):
        fake_json = {"collection": [self._make_item(title="P1"), self._make_item(title="P2", doi="10.1101/x2")]}
        with patch.object(self.src, "_get", return_value=_mock_response(json_data=fake_json)):
            papers = self.src.fetch_recent("", days=7, max_results=50)
        self.assertTrue(papers)
        for p in papers:
            self.assertEqual(p.source, "medrxiv")
            self.assertEqual(p.journal, "medrxiv")

    def test_fetch_recent_keyword_filter(self):
        items = [
            self._make_item(title="COVID Surveillance", doi="10.1101/001"),
            self._make_item(title="Unrelated Cardiology", abstract="heart stuff", doi="10.1101/002"),
        ]
        fake_json = {"collection": items}
        with patch.object(self.src, "_get", return_value=_mock_response(json_data=fake_json)):
            papers = self.src.fetch_recent("COVID", days=7, max_results=50)
        titles = [p.title for p in papers]
        self.assertIn("COVID Surveillance", titles)
        self.assertNotIn("Unrelated Cardiology", titles)

    def test_fetch_recent_respects_max_results(self):
        items = [self._make_item(title=f"COVID Paper {i}", doi=f"10.1101/{i:04d}") for i in range(20)]
        fake_json = {"collection": items}
        with patch.object(self.src, "_get", return_value=_mock_response(json_data=fake_json)):
            papers = self.src.fetch_recent("COVID", days=7, max_results=5)
        self.assertLessEqual(len(papers), 5)

    def test_pagination_stops_on_short_page(self):
        # A single page with fewer than 100 items should stop the loop.
        fake_json = {"collection": [self._make_item(title=f"COVID {i}", doi=f"10.1101/{i}") for i in range(3)]}
        mock = MagicMock(return_value=_mock_response(json_data=fake_json))
        with patch.object(self.src, "_get", mock):
            papers = self.src.fetch_recent("COVID", days=7, max_results=50)
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(len(papers), 3)


if __name__ == "__main__":
    unittest.main()
