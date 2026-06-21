"""Unit tests for data_pipeline/sources/ adapters.

Tests cover:
- PaperSource base contract (abstract method enforcement, throttle, _get)
- PubMedSource: XML parsing, structured abstract, MeSH categories, date coercion
- ArxivSource: Atom XML parsing, date filter, category extraction
- BioRxivSource: API response parsing, keyword matching, pagination termination
- SOURCE_REGISTRY: correct keys, all values are PaperSource subclasses
"""

import textwrap
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import xml.etree.ElementTree as ET

from ..models import Paper
from ..config import Config
from ..sources import SOURCE_REGISTRY, PaperSource
from ..sources.base import PaperSource as BasePaperSource
from ..sources.pubmed import PubMedSource
from ..sources.arxiv import ArxivSource
from ..sources.biorxiv import BioRxivSource


# ─── helpers ──────────────────────────────────────────────────────────────────

def _mock_response(json_data=None, text_data=None, status=200):
    """Return a minimal mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json = MagicMock(return_value=json_data)
    if text_data is not None:
        resp.text = text_data
    return resp


# ─── SOURCE_REGISTRY ──────────────────────────────────────────────────────────

class TestSourceRegistry(unittest.TestCase):
    def test_expected_sources_present(self):
        for name in ("pubmed", "arxiv", "biorxiv", "openalex", "chemrxiv", "medrxiv"):
            self.assertIn(name, SOURCE_REGISTRY)

    def test_nature_disabled(self):
        self.assertNotIn("nature", SOURCE_REGISTRY)

    def test_all_values_are_papersource_subclasses(self):
        for name, cls in SOURCE_REGISTRY.items():
            self.assertTrue(
                issubclass(cls, BasePaperSource),
                f"{name} is not a PaperSource subclass",
            )

    def test_names_match_class_name_attribute(self):
        for name, cls in SOURCE_REGISTRY.items():
            self.assertEqual(cls.name, name)


# ─── PaperSource base ─────────────────────────────────────────────────────────

class TestPaperSourceABC(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            BasePaperSource()  # type: ignore[abstract]

    def test_subclass_must_implement_fetch_recent(self):
        class Incomplete(BasePaperSource):
            name = "incomplete"
        with self.assertRaises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_subclass_with_implementation_instantiates(self):
        class Complete(BasePaperSource):
            name = "complete"
            def fetch_recent(self, query, *, days, max_results):
                return []
        src = Complete(Config())
        self.assertIsInstance(src, BasePaperSource)


# ─── PubMedSource ─────────────────────────────────────────────────────────────

class TestPubMedSource(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.src = PubMedSource(self.cfg)

    # ── _text helper ──
    def test_text_helper_found(self):
        root = ET.fromstring("<Root><PMID>12345</PMID></Root>")
        self.assertEqual(PubMedSource._text(root, ".//PMID"), "12345")

    def test_text_helper_missing(self):
        root = ET.fromstring("<Root/>")
        self.assertEqual(PubMedSource._text(root, ".//PMID"), "")

    def test_text_helper_default(self):
        root = ET.fromstring("<Root/>")
        self.assertEqual(PubMedSource._text(root, ".//X", default="fallback"), "fallback")

    # ── _parse_article ──
    def _make_pubmed_article_xml(
        self, pmid="11111", title="Test Title",
        abstract_text="Abstract body.",
        authors=None, journal="J Medicine",
        doi="10.1234/test", year="2024", month="Mar", day="15",
        mesh_terms=None,
    ):
        authors = authors or [("Smith", "J"), ("Doe", "A")]
        author_xml = "".join(
            f"<Author><LastName>{ln}</LastName><Initials>{ini}</Initials></Author>"
            for ln, ini in authors
        )
        mesh_xml = "".join(
            f"<MeshHeading><DescriptorName>{t}</DescriptorName></MeshHeading>"
            for t in (mesh_terms or [])
        )
        return f"""
        <PubmedArticle>
          <MedlineCitation>
            <PMID>{pmid}</PMID>
            <Article>
              <ArticleTitle>{title}</ArticleTitle>
              <Abstract><AbstractText>{abstract_text}</AbstractText></Abstract>
              <AuthorList>{author_xml}</AuthorList>
              <Journal><Title>{journal}</Title></Journal>
              <ArticleIdList>
                <ArticleId IdType="doi">{doi}</ArticleId>
              </ArticleIdList>
            </Article>
            <PubDate>
              <Year>{year}</Year><Month>{month}</Month><Day>{day}</Day>
            </PubDate>
            <MeshHeadingList>{mesh_xml}</MeshHeadingList>
          </MedlineCitation>
        </PubmedArticle>
        """

    def test_parse_article_basic(self):
        xml = self._make_pubmed_article_xml()
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertIsInstance(paper, Paper)
        self.assertEqual(paper.source, "pubmed")
        self.assertEqual(paper.source_id, "11111")
        self.assertEqual(paper.title, "Test Title")
        self.assertEqual(paper.abstract, "Abstract body.")
        self.assertEqual(paper.doi, "10.1234/test")
        self.assertEqual(paper.journal, "J Medicine")

    def test_parse_article_authors(self):
        xml = self._make_pubmed_article_xml(
            authors=[("Brown", "K"), ("Green", "L"), ("White", "M")]
        )
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertEqual(paper.authors, ["Brown K", "Green L", "White M"])

    def test_parse_article_url_includes_pmid(self):
        xml = self._make_pubmed_article_xml(pmid="99999")
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertIn("99999", paper.url)
        self.assertIn("pubmed.ncbi.nlm.nih.gov", paper.url)

    def test_parse_article_published_date(self):
        xml = self._make_pubmed_article_xml(year="2023", month="Jan", day="05")
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertIsNotNone(paper.published)
        self.assertTrue(paper.published.startswith("2023"))

    def test_parse_article_mesh_terms(self):
        xml = self._make_pubmed_article_xml(mesh_terms=["Neoplasms", "KRAS Protein"])
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertIn("Neoplasms", paper.categories)
        self.assertIn("KRAS Protein", paper.categories)

    def test_parse_structured_abstract(self):
        """Structured abstracts with labeled sections should be joined."""
        xml = """
        <PubmedArticle>
          <MedlineCitation>
            <PMID>55555</PMID>
            <Article>
              <ArticleTitle>Structured</ArticleTitle>
              <Abstract>
                <AbstractText Label="BACKGROUND">Some background.</AbstractText>
                <AbstractText Label="METHODS">Some methods.</AbstractText>
                <AbstractText Label="RESULTS">Some results.</AbstractText>
              </Abstract>
              <AuthorList/>
              <Journal><Title>J</Title></Journal>
              <ArticleIdList/>
            </Article>
            <PubDate><Year>2024</Year></PubDate>
            <MeshHeadingList/>
          </MedlineCitation>
        </PubmedArticle>
        """
        art = ET.fromstring(xml)
        paper = self.src._parse_article(art)
        self.assertIn("BACKGROUND:", paper.abstract)
        self.assertIn("METHODS:", paper.abstract)
        self.assertIn("RESULTS:", paper.abstract)

    def test_common_params_with_key(self):
        cfg = Config(ncbi_api_key="mykey123")
        src = PubMedSource(cfg)
        params = src._common_params()
        self.assertEqual(params["api_key"], "mykey123")

    def test_common_params_without_key(self):
        cfg = Config(ncbi_api_key=None)
        src = PubMedSource(cfg)
        params = src._common_params()
        self.assertNotIn("api_key", params)

    def test_fetch_recent_returns_empty_on_no_pmids(self):
        """If esearch returns no IDs, fetch_recent returns []."""
        src = PubMedSource(Config())
        with patch.object(src, "_search", return_value=[]):
            result = src.fetch_recent("test", days=7, max_results=10)
        self.assertEqual(result, [])

    def test_fetch_recent_calls_fetch_details(self):
        src = PubMedSource(Config())
        pmids = ["1", "2", "3"]
        fake_papers = [Paper(source="pubmed", source_id=p, title=f"T{p}") for p in pmids]
        with patch.object(src, "_search", return_value=pmids), \
             patch.object(src, "_fetch_details", return_value=fake_papers) as mock_fd:
            result = src.fetch_recent("test", days=7, max_results=10)
        mock_fd.assert_called_once_with(pmids)
        self.assertEqual(result, fake_papers)


# ─── ArxivSource ──────────────────────────────────────────────────────────────

ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
ATOM = f"{{{ATOM_NS}}}"
ARXIV_ATOM = f"{{{ARXIV_NS}}}"


def _make_arxiv_atom(entries: list[dict]) -> str:
    """Build minimal Atom XML feed for arXiv tests using proper namespace prefixes."""
    entry_xmls = []
    for e in entries:
        published = e.get("published", "2024-06-15T00:00:00Z")
        authors_xml = "".join(
            f"<atom:author><atom:name>{a}</atom:name></atom:author>"
            for a in e.get("authors", ["Smith J"])
        )
        cats_xml = "".join(
            f'<atom:category term="{c}"/>'
            for c in e.get("categories", [])
        )
        doi_xml = (
            f'<arxiv:doi>{e["doi"]}</arxiv:doi>'
            if e.get("doi") else ""
        )
        entry_id = e.get("id", "http://arxiv.org/abs/2406.00001v1")
        title = e.get("title", "A Title")
        abstract = e.get("abstract", "Abstract text.")
        entry_xmls.append(f"""
        <atom:entry>
          <atom:id>{entry_id}</atom:id>
          <atom:title>{title}</atom:title>
          <atom:summary>{abstract}</atom:summary>
          <atom:published>{published}</atom:published>
          {authors_xml}
          {cats_xml}
          {doi_xml}
        </atom:entry>
        """)
    entries_joined = "".join(entry_xmls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <atom:feed
      xmlns:atom="{ATOM_NS}"
      xmlns:arxiv="{ARXIV_NS}">
      {entries_joined}
    </atom:feed>
    """


class TestArxivSource(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.src = ArxivSource(self.cfg)

    def _entry_xml(self, **kwargs) -> ET.Element:
        atom_str = _make_arxiv_atom([kwargs])
        root = ET.fromstring(atom_str)
        return root.find(f"{ATOM}entry")  # ATOM = "{http://www.w3.org/2005/Atom}"

    def test_parse_entry_basic(self):
        entry = self._entry_xml(
            id="http://arxiv.org/abs/2406.11111v1",
            title="  My   Title  ",
            abstract="  Some   abstract.  ",
            authors=["Smith J", "Doe A"],
        )
        paper = self.src._parse_entry(entry)
        self.assertEqual(paper.source, "arxiv")
        self.assertEqual(paper.title, "My Title")
        self.assertEqual(paper.abstract, "Some abstract.")
        self.assertIn("Smith J", paper.authors)
        self.assertIn("Doe A", paper.authors)

    def test_parse_entry_source_id_from_url(self):
        entry = self._entry_xml(id="http://arxiv.org/abs/2406.12345v2")
        paper = self.src._parse_entry(entry)
        self.assertEqual(paper.source_id, "2406.12345v2")

    def test_parse_entry_categories(self):
        entry = self._entry_xml(categories=["q-bio.QM", "cs.LG"])
        paper = self.src._parse_entry(entry)
        self.assertIn("q-bio.QM", paper.categories)
        self.assertIn("cs.LG", paper.categories)

    def test_parse_entry_doi_extracted(self):
        entry = self._entry_xml(doi="10.1234/nature2024")
        paper = self.src._parse_entry(entry)
        self.assertEqual(paper.doi, "10.1234/nature2024")

    def test_parse_entry_no_doi_is_none(self):
        entry = self._entry_xml()
        paper = self.src._parse_entry(entry)
        self.assertIsNone(paper.doi)

    def test_parse_entry_published_datetime_stored_in_raw(self):
        entry = self._entry_xml(published="2024-06-15T12:00:00Z")
        paper = self.src._parse_entry(entry)
        self.assertIn("_published_dt", paper.raw)
        self.assertIsNotNone(paper.raw["_published_dt"])

    def test_fetch_recent_filters_old_entries(self):
        """Entries older than the cutoff should be excluded."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        new_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        atom_xml = _make_arxiv_atom([
            {"id": "http://arxiv.org/abs/2406.00001v1", "published": new_date,
             "title": "New Paper"},
            {"id": "http://arxiv.org/abs/2406.00002v1", "published": old_date,
             "title": "Old Paper"},
        ])
        with patch.object(self.src, "_get", return_value=_mock_response(text_data=atom_xml)):
            papers = self.src.fetch_recent("test", days=7, max_results=10)
        titles = [p.title for p in papers]
        self.assertIn("New Paper", titles)
        self.assertNotIn("Old Paper", titles)

    def test_fetch_recent_respects_max_results(self):
        """Should return at most max_results papers."""
        new_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries = [
            {"id": f"http://arxiv.org/abs/2406.{i:05d}v1",
             "published": new_date, "title": f"Paper {i}"}
            for i in range(20)
        ]
        atom_xml = _make_arxiv_atom(entries)
        with patch.object(self.src, "_get", return_value=_mock_response(text_data=atom_xml)):
            papers = self.src.fetch_recent("test", days=7, max_results=5)
        self.assertLessEqual(len(papers), 5)


# ─── BioRxivSource ────────────────────────────────────────────────────────────

class TestBioRxivSource(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.src = BioRxivSource(self.cfg)

    def _make_item(self, **kwargs) -> dict:
        return {
            "doi": kwargs.get("doi", "10.1101/2024.01.01.000001"),
            "title": kwargs.get("title", "A bioRxiv Preprint"),
            "abstract": kwargs.get("abstract", "Some abstract content."),
            "authors": kwargs.get("authors", "Smith J; Doe A"),
            "date": kwargs.get("date", "2024-06-01"),
            "category": kwargs.get("category", "bioinformatics"),
            "version": kwargs.get("version", "1"),
        }

    def test_parse_item_basic(self):
        item = self._make_item()
        paper = self.src._parse_item(item)
        self.assertIsInstance(paper, Paper)
        self.assertEqual(paper.source, "biorxiv")
        self.assertEqual(paper.title, "A bioRxiv Preprint")
        self.assertEqual(paper.abstract, "Some abstract content.")
        self.assertEqual(paper.doi, "10.1101/2024.01.01.000001")

    def test_parse_item_authors_split(self):
        item = self._make_item(authors="Smith J; Doe A; Lee K")
        paper = self.src._parse_item(item)
        self.assertEqual(paper.authors, ["Smith J", "Doe A", "Lee K"])

    def test_parse_item_category_in_categories(self):
        item = self._make_item(category="neuroscience")
        paper = self.src._parse_item(item)
        self.assertIn("neuroscience", paper.categories)

    def test_parse_item_url_uses_doi(self):
        item = self._make_item(doi="10.1101/2024.01.01.000001")
        paper = self.src._parse_item(item)
        self.assertIn("10.1101/2024.01.01.000001", paper.url)

    def test_parse_item_no_doi(self):
        item = self._make_item(doi="", title="No DOI Paper")
        item["doi"] = ""
        paper = self.src._parse_item(item)
        self.assertIsNone(paper.doi)
        self.assertIsNone(paper.url)

    def test_matches_any_term_in_haystack(self):
        paper = Paper(
            source="biorxiv", source_id="1",
            title="KRAS G12C mutation treatment",
            abstract="A study of adagrasib in lung cancer.",
            categories=["oncology"],
        )
        self.assertTrue(BioRxivSource._matches(paper, ["kras"]))
        self.assertTrue(BioRxivSource._matches(paper, ["adagrasib"]))
        self.assertTrue(BioRxivSource._matches(paper, ["lung"]))
        self.assertFalse(BioRxivSource._matches(paper, ["microbiome"]))

    def test_matches_empty_terms_always_true(self):
        paper = Paper(source="biorxiv", source_id="1", title="Anything")
        self.assertTrue(BioRxivSource._matches(paper, []))

    def test_matches_case_insensitive(self):
        paper = Paper(source="biorxiv", source_id="1", title="KRAS Inhibitor Study")
        self.assertTrue(BioRxivSource._matches(paper, ["kras"]))

    def test_fetch_page_returns_collection(self):
        fake_items = [self._make_item(title=f"Paper {i}") for i in range(5)]
        fake_json = {"collection": fake_items}
        with patch.object(self.src, "_get", return_value=_mock_response(json_data=fake_json)):
            result = self.src._fetch_page(date.today() - timedelta(days=7), date.today(), 0)
        self.assertEqual(len(result), 5)

    def test_fetch_page_empty_collection(self):
        with patch.object(self.src, "_get", return_value=_mock_response(json_data={})):
            result = self.src._fetch_page(date.today() - timedelta(days=7), date.today(), 0)
        self.assertEqual(result, [])

    def test_fetch_recent_filters_by_keyword(self):
        items_matching = [
            self._make_item(title="KRAS G12C Paper", doi="10.1101/001"),
            self._make_item(title="Another KRAS Study", doi="10.1101/002"),
        ]
        items_non_matching = [
            self._make_item(title="Unrelated Topic", abstract="Physics only", doi="10.1101/003"),
        ]
        all_items = items_matching + items_non_matching

        def fake_fetch_page(start, end, cursor):
            if cursor == 0:
                return all_items
            return []

        with patch.object(self.src, "_fetch_page", side_effect=fake_fetch_page):
            papers = self.src.fetch_recent("KRAS", days=7, max_results=50)

        titles = [p.title for p in papers]
        self.assertIn("KRAS G12C Paper", titles)
        self.assertIn("Another KRAS Study", titles)
        self.assertNotIn("Unrelated Topic", titles)

    def test_fetch_recent_respects_max_results(self):
        items = [self._make_item(title=f"KRAS Paper {i}", doi=f"10.1101/{i:04d}") for i in range(20)]

        def fake_fetch_page(start, end, cursor):
            return items[cursor:cursor + 100] if cursor < len(items) else []

        with patch.object(self.src, "_fetch_page", side_effect=fake_fetch_page):
            papers = self.src.fetch_recent("KRAS", days=7, max_results=5)

        self.assertLessEqual(len(papers), 5)

    def test_server_attribute_default(self):
        self.assertEqual(self.src.server, "biorxiv")

    def test_server_medrxiv(self):
        src = BioRxivSource(self.cfg, server="medrxiv")
        self.assertEqual(src.server, "medrxiv")


if __name__ == "__main__":
    unittest.main()
