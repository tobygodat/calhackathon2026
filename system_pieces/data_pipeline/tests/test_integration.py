"""Integration tests for the data pipeline.

These tests verify the components work together correctly as a system.
All external HTTP calls are mocked — no live network traffic during CI.

Integration scenarios:
1. Full pipeline round-trip: mock API responses → FetchResult with deduped papers
2. Multi-source fan-out with one source failing → others still contribute
3. CLI arg parsing → DataPipeline invocation (without network calls)
4. Paper model → to_dict → round-trip JSON serialization
5. Config → PaperSource construction → correct rate-limit wiring
6. End-to-end dedupe across sources: bioRxiv preprint + Nature publication same DOI
7. FetchResult counting accuracy after multi-source fetch
"""

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from ..config import Config
from ..models import Paper, _coerce_date
from ..pipeline import DataPipeline, FetchResult
from ..sources import SOURCE_REGISTRY
from ..sources.pubmed import PubMedSource
from ..sources.arxiv import ArxivSource
from ..sources.biorxiv import BioRxivSource


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_paper(source="pubmed", source_id="1", title="Test Paper",
                abstract="", doi=None, published=None) -> Paper:
    return Paper(source=source, source_id=source_id, title=title,
                 abstract=abstract, doi=doi, published=published)


def _pubmed_xml_response(papers: list[dict]) -> str:
    """Minimal PubMed efetch XML for integration tests."""
    articles = []
    for p in papers:
        authors_xml = "".join(
            f"<Author><LastName>{a}</LastName><Initials>X</Initials></Author>"
            for a in p.get("authors", ["Smith"])
        )
        abstract_xml = (
            f"<Abstract><AbstractText>{p['abstract']}</AbstractText></Abstract>"
            if p.get("abstract") else ""
        )
        doi_xml = (
            f'<ArticleId IdType="doi">{p["doi"]}</ArticleId>'
            if p.get("doi") else ""
        )
        articles.append(f"""
        <PubmedArticle>
          <MedlineCitation>
            <PMID>{p.get("pmid", "00001")}</PMID>
            <Article>
              <ArticleTitle>{p.get("title", "A Study")}</ArticleTitle>
              {abstract_xml}
              <AuthorList>{authors_xml}</AuthorList>
              <Journal><Title>{p.get("journal", "Journal of Tests")}</Title></Journal>
              <ArticleIdList>{doi_xml}</ArticleIdList>
            </Article>
            <PubDate>
              <Year>{p.get("year", "2024")}</Year>
              <Month>Jan</Month>
              <Day>01</Day>
            </PubDate>
            <MeshHeadingList/>
          </MedlineCitation>
        </PubmedArticle>
        """)
    return f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>"


def _arxiv_xml_response(papers: list[dict]) -> str:
    """Minimal arXiv Atom XML feed for integration tests."""
    ATOM_NS = "http://www.w3.org/2005/Atom"
    ARXIV_NS = "http://arxiv.org/schemas/atom"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entries = []
    for p in papers:
        published = p.get("published", now_str)
        authors_xml = "".join(
            f"<atom:author><atom:name>{a}</atom:name></atom:author>"
            for a in p.get("authors", ["Smith J"])
        )
        doi_xml = f'<arxiv:doi>{p["doi"]}</arxiv:doi>' if p.get("doi") else ""
        entries.append(f"""
        <atom:entry>
          <atom:id>{p.get("id", "http://arxiv.org/abs/2406.00001v1")}</atom:id>
          <atom:title>{p.get("title", "A Title")}</atom:title>
          <atom:summary>{p.get("abstract", "Abstract.")}</atom:summary>
          <atom:published>{published}</atom:published>
          {authors_xml}
          {doi_xml}
        </atom:entry>
        """)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <atom:feed xmlns:atom="{ATOM_NS}" xmlns:arxiv="{ARXIV_NS}">
      {"".join(entries)}
    </atom:feed>
    """


def _biorxiv_json_response(papers: list[dict]) -> dict:
    """Minimal bioRxiv API response for integration tests."""
    items = []
    for p in papers:
        items.append({
            "doi": p.get("doi", "10.1101/2024.01.01.000001"),
            "title": p.get("title", "A Preprint"),
            "abstract": p.get("abstract", "Abstract here."),
            "authors": p.get("authors", "Smith J; Doe A"),
            "date": p.get("date", date.today().isoformat()),
            "category": p.get("category", "bioinformatics"),
            "version": "1",
        })
    return {"collection": items}


# ─── Integration Test 1: PubMed end-to-end ────────────────────────────────────

class TestPubMedIntegration(unittest.TestCase):
    def setUp(self):
        self.config = Config(contact_email="test@test.com")
        self.src = PubMedSource(self.config)

    def test_full_round_trip_single_paper(self):
        """esearch returns PMIDs → efetch returns XML → Paper objects produced."""
        search_json = {"esearchresult": {"idlist": ["11111"]}}
        fetch_xml = _pubmed_xml_response([{
            "pmid": "11111",
            "title": "KRAS G12C Resistance Mechanisms",
            "abstract": "Patients with KRAS G12C mutations...",
            "authors": ["Smith", "Jones"],
            "journal": "Nature Medicine",
            "doi": "10.1038/nm.2024.001",
            "year": "2024",
        }])

        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.json = MagicMock(return_value=search_json)

        fetch_resp = MagicMock()
        fetch_resp.raise_for_status = MagicMock()
        fetch_resp.text = fetch_xml

        call_count = [0]
        def fake_get(url, **kwargs):
            call_count[0] += 1
            if "esearch" in url:
                return search_resp
            return fetch_resp

        with patch.object(self.src, "_get", side_effect=fake_get):
            papers = self.src.fetch_recent("KRAS G12C", days=7, max_results=10)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source, "pubmed")
        self.assertEqual(papers[0].source_id, "11111")
        self.assertEqual(papers[0].title, "KRAS G12C Resistance Mechanisms")
        self.assertEqual(papers[0].doi, "10.1038/nm.2024.001")
        self.assertEqual(papers[0].journal, "Nature Medicine")
        self.assertTrue(any("Smith" in a for a in papers[0].authors))
        self.assertTrue(papers[0].has_abstract)
        self.assertEqual(call_count[0], 2)  # esearch + efetch

    def test_empty_search_results_no_efetch(self):
        """If esearch returns no PMIDs, efetch should never be called."""
        search_json = {"esearchresult": {"idlist": []}}
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.json = MagicMock(return_value=search_json)

        efetch_called = [False]
        def fake_get(url, **kwargs):
            if "efetch" in url:
                efetch_called[0] = True
            return search_resp

        with patch.object(self.src, "_get", side_effect=fake_get):
            papers = self.src.fetch_recent("nonexistent topic xyz", days=7, max_results=10)

        self.assertEqual(papers, [])
        self.assertFalse(efetch_called[0])


# ─── Integration Test 2: ArXiv end-to-end ─────────────────────────────────────

class TestArxivIntegration(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.src = ArxivSource(self.config)

    def test_full_round_trip(self):
        """Atom XML response → filtered Paper list."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = _arxiv_xml_response([{
            "id": "http://arxiv.org/abs/2406.12345v1",
            "title": "Quantum Biology in KRAS signaling",
            "abstract": "We study quantum effects in protein folding.",
            "authors": ["Feynman R", "Dirac P"],
            "published": now_str,
            "doi": "10.48550/arXiv.2406.12345",
        }])

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = xml

        with patch.object(self.src, "_get", return_value=mock_resp):
            papers = self.src.fetch_recent("KRAS signaling", days=7, max_results=10)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].source, "arxiv")
        self.assertEqual(papers[0].source_id, "2406.12345v1")
        self.assertIn("Feynman R", papers[0].authors)
        self.assertEqual(papers[0].doi, "10.48550/arXiv.2406.12345")

    def test_date_cutoff_integration(self):
        """Old entries are excluded; only recent ones returned."""
        old_pub = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_pub = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = _arxiv_xml_response([
            {"id": "http://arxiv.org/abs/old.1v1", "title": "Old Paper", "published": old_pub},
            {"id": "http://arxiv.org/abs/new.1v1", "title": "New Paper", "published": new_pub},
        ])

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = xml

        with patch.object(self.src, "_get", return_value=mock_resp):
            papers = self.src.fetch_recent("test", days=7, max_results=50)

        titles = [p.title for p in papers]
        self.assertIn("New Paper", titles)
        self.assertNotIn("Old Paper", titles)


# ─── Integration Test 3: BioRxiv end-to-end ───────────────────────────────────

class TestBioRxivIntegration(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.src = BioRxivSource(self.config)

    def test_full_round_trip(self):
        """API JSON response → keyword-filtered Paper list."""
        api_json = _biorxiv_json_response([
            {"title": "KRAS G12C in Lung Cancer", "doi": "10.1101/001",
             "abstract": "KRAS mutations are common in lung adenocarcinoma.",
             "authors": "Chen L; Park S"},
            {"title": "Unrelated Geology Paper", "doi": "10.1101/002",
             "abstract": "Sediment core analysis reveals ancient seafloors.",
             "authors": "Brown K"},
        ])
        api_resp = MagicMock()
        api_resp.raise_for_status = MagicMock()
        api_resp.json = MagicMock(return_value=api_json)

        with patch.object(self.src, "_get", return_value=api_resp):
            papers = self.src.fetch_recent("KRAS lung", days=7, max_results=50)

        titles = [p.title for p in papers]
        self.assertIn("KRAS G12C in Lung Cancer", titles)
        self.assertNotIn("Unrelated Geology Paper", titles)

    def test_authors_parsed_correctly(self):
        """Semicolon-separated authors string is split into a list."""
        api_json = _biorxiv_json_response([
            {"title": "KRAS Study", "authors": "Smith J; Jones A; Lee B; Park C",
             "doi": "10.1101/003"}
        ])
        api_resp = MagicMock()
        api_resp.raise_for_status = MagicMock()
        api_resp.json = MagicMock(return_value=api_json)

        with patch.object(self.src, "_get", return_value=api_resp):
            papers = self.src.fetch_recent("KRAS", days=7, max_results=10)

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].authors, ["Smith J", "Jones A", "Lee B", "Park C"])


# ─── Integration Test 4: Multi-source pipeline ────────────────────────────────

class TestMultiSourcePipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def _make_mock_source(self, papers, name="mock"):
        """Create a mock source that returns fixed papers."""
        src = MagicMock()
        src.fetch_recent = MagicMock(return_value=papers)
        return src

    def test_two_sources_results_combined(self):
        """Papers from two sources are combined and returned."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = self.config
        pipe.sources = {
            "pubmed": self._make_mock_source([
                _make_paper("pubmed", "1", "Alpha Study", abstract="Alpha abstract",
                            published="2024-06-01"),
            ]),
            "arxiv": self._make_mock_source([
                _make_paper("arxiv", "2", "Beta Study", abstract="Beta abstract",
                            published="2024-05-15"),
            ]),
        }

        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertEqual(len(result.papers), 2)
        self.assertEqual(result.counts["pubmed"], 1)
        self.assertEqual(result.counts["arxiv"], 1)

    def test_cross_source_doi_dedup(self):
        """Same DOI from two sources → one paper, longer abstract wins."""
        shared_doi = "10.1038/shared.2024.001"
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = self.config
        pipe.sources = {
            "pubmed": self._make_mock_source([
                _make_paper("pubmed", "111", "Shared Paper",
                            doi=shared_doi, abstract="Short pubmed abstract."),
            ]),
            "biorxiv": self._make_mock_source([
                _make_paper("biorxiv", "bior:001", "Shared Paper",
                            doi=shared_doi,
                            abstract="Much longer bioRxiv abstract that should win dedup."),
            ]),
        }

        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertEqual(len(result.papers), 1)
        self.assertIn("longer", result.papers[0].abstract)

    def test_one_source_failure_others_succeed(self):
        """If one source raises an exception, the others still return results."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = self.config

        failing_src = MagicMock()
        failing_src.fetch_recent = MagicMock(
            side_effect=ConnectionError("Network unreachable")
        )
        working_src = self._make_mock_source([
            _make_paper("arxiv", "a1", "Working Source Paper", abstract="Found it."),
        ])

        pipe.sources = {"pubmed": failing_src, "arxiv": working_src}
        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)

        self.assertIn("pubmed", result.errors)
        self.assertIn("ConnectionError", result.errors["pubmed"])
        self.assertEqual(len(result.papers), 1)
        self.assertEqual(result.papers[0].title, "Working Source Paper")

    def test_all_sources_fail_empty_result(self):
        """All sources failing → empty papers list, all sources in errors."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = self.config
        pipe.sources = {
            "pubmed": MagicMock(
                fetch_recent=MagicMock(side_effect=RuntimeError("PubMed down"))
            ),
            "arxiv": MagicMock(
                fetch_recent=MagicMock(side_effect=RuntimeError("arXiv down"))
            ),
        }

        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        self.assertEqual(result.papers, [])
        self.assertIn("pubmed", result.errors)
        self.assertIn("arxiv", result.errors)

    def test_results_sorted_newest_first(self):
        """Final output is newest-first across all sources."""
        pipe = DataPipeline.__new__(DataPipeline)
        pipe.config = self.config
        pipe.sources = {
            "pubmed": self._make_mock_source([
                _make_paper("pubmed", "1", "Old Pubmed", published="2022-01-01"),
                _make_paper("pubmed", "2", "New Pubmed", published="2024-06-15"),
            ]),
            "arxiv": self._make_mock_source([
                _make_paper("arxiv", "3", "Mid Arxiv", published="2023-03-10"),
            ]),
        }

        result = pipe.fetch("test", days=7, max_per_source=50, parallel=False)
        dates = [p.published for p in result.papers if p.published]
        self.assertEqual(dates, sorted(dates, reverse=True))


# ─── Integration Test 5: JSON serialization round-trip ────────────────────────

class TestJsonSerializationIntegration(unittest.TestCase):
    def test_paper_to_dict_json_serializable(self):
        """to_dict() output must be directly JSON-serializable."""
        p = Paper(
            source="pubmed",
            source_id="99999",
            title="Serialization Test Paper",
            abstract="This paper tests JSON output.",
            authors=["Smith J", "Doe A"],
            doi="10.1234/test.2024",
            url="https://pubmed.ncbi.nlm.nih.gov/99999/",
            journal="Journal of Tests",
            published="2024-06-15",
            categories=["Neoplasms", "KRAS Protein"],
            raw={"internal": "data"},
        )
        d = p.to_dict()
        # Must not raise
        serialized = json.dumps(d)
        recovered = json.loads(serialized)

        self.assertEqual(recovered["source"], "pubmed")
        self.assertEqual(recovered["title"], "Serialization Test Paper")
        self.assertEqual(recovered["uid"], "doi:10.1234/test.2024")
        self.assertNotIn("raw", recovered)
        self.assertEqual(recovered["authors"], ["Smith J", "Doe A"])

    def test_fetch_result_papers_all_serializable(self):
        """All papers from a FetchResult must be JSON-serializable."""
        papers = [
            Paper(source="pubmed", source_id=str(i), title=f"Paper {i}",
                  abstract="abstract", doi=f"10.1/{i}", published="2024-01-01")
            for i in range(5)
        ]
        result = FetchResult(papers=papers, counts={"pubmed": 5}, errors={})

        payload = {
            "papers": [p.to_dict() for p in result.papers],
            "counts": result.counts,
            "errors": result.errors,
        }
        serialized = json.dumps(payload)
        recovered = json.loads(serialized)
        self.assertEqual(len(recovered["papers"]), 5)


# ─── Integration Test 6: Config → Source wiring ───────────────────────────────

class TestConfigSourceWiringIntegration(unittest.TestCase):
    def test_config_propagates_to_sources(self):
        """Config values passed to DataPipeline are accessible in each source."""
        cfg = Config(
            contact_email="team@baskr.io",
            ncbi_api_key="test_ncbi_key",
        )
        pipe = DataPipeline(sources=["pubmed"], config=cfg)
        pubmed_src = pipe.sources["pubmed"]
        # The source should inherit the config
        self.assertEqual(pubmed_src.config.contact_email, "team@baskr.io")
        self.assertEqual(pubmed_src.config.ncbi_api_key, "test_ncbi_key")

    def test_ncbi_key_raises_rate_limit_in_source(self):
        """PubMedSource rate limit reflects ncbi_api_key presence."""
        cfg_with_key = Config(ncbi_api_key="mykey")
        cfg_no_key = Config(ncbi_api_key=None)

        src_with_key = PubMedSource(cfg_with_key)
        src_no_key = PubMedSource(cfg_no_key)

        # 10 rps → 0.1s interval; 3 rps → ~0.333s interval
        self.assertAlmostEqual(src_with_key._min_interval, 1.0 / 10.0, places=3)
        self.assertAlmostEqual(src_no_key._min_interval, 1.0 / 3.0, places=3)

    def test_session_user_agent_set(self):
        """HTTP session User-Agent includes tool name and contact email."""
        cfg = Config(tool_name="test-tool", contact_email="dev@test.com")
        pipe = DataPipeline(sources=["pubmed"], config=cfg)
        src = pipe.sources["pubmed"]
        ua = src._session.headers.get("User-Agent", "")
        self.assertIn("test-tool", ua)
        self.assertIn("dev@test.com", ua)


# ─── Integration Test 7: Source registry completeness ─────────────────────────

class TestSourceRegistryIntegration(unittest.TestCase):
    def test_all_registry_sources_instantiate(self):
        """Every source in SOURCE_REGISTRY instantiates without error."""
        cfg = Config()
        for name, cls in SOURCE_REGISTRY.items():
            with self.subTest(source=name):
                src = cls(cfg)
                self.assertIsNotNone(src)
                self.assertEqual(src.name, name)

    def test_pipeline_with_all_sources_initializes(self):
        """DataPipeline() with no args creates one source per registry entry."""
        pipe = DataPipeline()
        self.assertEqual(set(pipe.sources.keys()), set(SOURCE_REGISTRY.keys()))

    def test_pipeline_with_single_source_subset(self):
        """DataPipeline(['pubmed']) has only PubMed source."""
        pipe = DataPipeline(sources=["pubmed"])
        self.assertEqual(list(pipe.sources.keys()), ["pubmed"])
        self.assertIsInstance(pipe.sources["pubmed"], PubMedSource)

    def test_pipeline_rejects_mix_of_valid_and_invalid(self):
        """If even one source name is invalid, constructor raises ValueError."""
        with self.assertRaises(ValueError):
            DataPipeline(sources=["pubmed", "invalid_source"])


if __name__ == "__main__":
    unittest.main()
