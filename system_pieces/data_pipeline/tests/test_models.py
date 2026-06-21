"""Unit tests for data_pipeline/models.py.

Tests cover:
- Paper dataclass construction, defaults, and field types
- Paper.uid — DOI-preferred, falls back to source:source_id
- Paper.fingerprint — SHA-1 of normalized title
- Paper.has_abstract — truthy/falsy variations
- Paper.citation() — formatting edge-cases
- Paper.to_dict() — serialization, uid injection, no 'raw' key
- _coerce_date() — all supported input forms + edge cases
"""

import hashlib
import unittest
from datetime import date, datetime

from ..models import Paper, _coerce_date


class TestPaperDefaults(unittest.TestCase):
    def _minimal(self, **kwargs) -> Paper:
        base = dict(source="pubmed", source_id="12345", title="A Study")
        base.update(kwargs)
        return Paper(**base)

    def test_defaults(self):
        p = self._minimal()
        self.assertEqual(p.abstract, "")
        self.assertEqual(p.authors, [])
        self.assertIsNone(p.doi)
        self.assertIsNone(p.url)
        self.assertIsNone(p.journal)
        self.assertIsNone(p.published)
        self.assertEqual(p.categories, [])
        self.assertEqual(p.raw, {})

    def test_explicit_values(self):
        p = Paper(
            source="arxiv",
            source_id="2406.00001",
            title="A Test Paper",
            abstract="A short abstract.",
            authors=["Smith J", "Doe A"],
            doi="10.1000/xyz123",
            url="http://arxiv.org/abs/2406.00001",
            journal="arXiv",
            published="2024-06-15",
            categories=["q-bio.QM"],
            raw={"extra": "data"},
        )
        self.assertEqual(p.source, "arxiv")
        self.assertEqual(p.abstract, "A short abstract.")
        self.assertEqual(p.authors, ["Smith J", "Doe A"])
        self.assertEqual(p.doi, "10.1000/xyz123")


class TestPaperUID(unittest.TestCase):
    def test_uid_doi_preferred(self):
        p = Paper(source="pubmed", source_id="99999", title="T",
                  doi="10.1234/test")
        self.assertEqual(p.uid, "doi:10.1234/test")

    def test_uid_doi_lowercased(self):
        p = Paper(source="pubmed", source_id="99999", title="T",
                  doi="10.1234/Test.DOI")
        self.assertEqual(p.uid, "doi:10.1234/test.doi")

    def test_uid_no_doi(self):
        p = Paper(source="biorxiv", source_id="abc123", title="T")
        self.assertEqual(p.uid, "biorxiv:abc123")

    def test_uid_empty_doi_treated_as_none(self):
        # doi=None (default) → source-based uid
        p = Paper(source="arxiv", source_id="2406.12345v1", title="T")
        self.assertEqual(p.uid, "arxiv:2406.12345v1")


class TestPaperFingerprint(unittest.TestCase):
    def _expected_fp(self, title: str) -> str:
        norm = "".join(ch for ch in title.lower() if ch.isalnum())
        return hashlib.sha1(norm.encode()).hexdigest()

    def test_fingerprint_basic(self):
        p = Paper(source="pubmed", source_id="1", title="KRAS G12C Inhibition")
        self.assertEqual(p.fingerprint, self._expected_fp("KRAS G12C Inhibition"))

    def test_fingerprint_case_insensitive(self):
        p1 = Paper(source="pubmed", source_id="1", title="Gut Microbiome")
        p2 = Paper(source="arxiv", source_id="2", title="gut microbiome")
        self.assertEqual(p1.fingerprint, p2.fingerprint)

    def test_fingerprint_punctuation_stripped(self):
        p1 = Paper(source="pubmed", source_id="1", title="Title: A Review")
        p2 = Paper(source="pubmed", source_id="2", title="Title A Review")
        self.assertEqual(p1.fingerprint, p2.fingerprint)

    def test_fingerprint_is_40_hex(self):
        p = Paper(source="pubmed", source_id="1", title="Test Title")
        self.assertRegex(p.fingerprint, r"^[0-9a-f]{40}$")

    def test_fingerprint_different_titles_differ(self):
        p1 = Paper(source="pubmed", source_id="1", title="Study One")
        p2 = Paper(source="pubmed", source_id="2", title="Study Two")
        self.assertNotEqual(p1.fingerprint, p2.fingerprint)


class TestPaperHasAbstract(unittest.TestCase):
    def test_has_abstract_true(self):
        p = Paper(source="pubmed", source_id="1", title="T", abstract="Real text here.")
        self.assertTrue(p.has_abstract)

    def test_has_abstract_empty_string(self):
        p = Paper(source="pubmed", source_id="1", title="T", abstract="")
        self.assertFalse(p.has_abstract)

    def test_has_abstract_whitespace_only(self):
        p = Paper(source="pubmed", source_id="1", title="T", abstract="   \n\t  ")
        self.assertFalse(p.has_abstract)

    def test_has_abstract_default(self):
        p = Paper(source="pubmed", source_id="1", title="T")
        self.assertFalse(p.has_abstract)


class TestPaperCitation(unittest.TestCase):
    def test_single_author(self):
        p = Paper(source="pubmed", source_id="1", title="The Study",
                  authors=["Smith J"], journal="Nature", published="2024-03-15")
        self.assertEqual(p.citation(), "Smith J (2024). The Study. Nature.")

    def test_multiple_authors_et_al(self):
        p = Paper(source="pubmed", source_id="1", title="T",
                  authors=["Smith J", "Doe A"], journal="Journal", published="2023-01-01")
        self.assertIn("et al.", p.citation())
        self.assertTrue(p.citation().startswith("Smith J et al."))

    def test_no_authors_unknown(self):
        p = Paper(source="arxiv", source_id="1", title="T", published="2024-01-01")
        self.assertIn("Unknown", p.citation())

    def test_no_journal_uses_source(self):
        p = Paper(source="biorxiv", source_id="1", title="T",
                  authors=["Lee K"], published="2024-01-01")
        self.assertIn("Biorxiv", p.citation())

    def test_no_published_year_empty(self):
        p = Paper(source="pubmed", source_id="1", title="T",
                  authors=["Smith J"], journal="J", published=None)
        self.assertIn("()", p.citation())

    def test_year_extraction_from_full_date(self):
        p = Paper(source="pubmed", source_id="1", title="T",
                  authors=["A B"], journal="J", published="2022-07-04")
        self.assertIn("2022", p.citation())


class TestPaperToDict(unittest.TestCase):
    def test_uid_injected(self):
        p = Paper(source="pubmed", source_id="7777", title="T", doi="10.1/abc")
        d = p.to_dict()
        self.assertEqual(d["uid"], "doi:10.1/abc")

    def test_raw_excluded(self):
        p = Paper(source="pubmed", source_id="1", title="T", raw={"secret": True})
        d = p.to_dict()
        self.assertNotIn("raw", d)

    def test_standard_fields_present(self):
        p = Paper(source="arxiv", source_id="2406.1", title="Test",
                  abstract="Abstract text.", authors=["A", "B"],
                  published="2024-06-01", journal="arXiv",
                  categories=["cs.AI"])
        d = p.to_dict()
        for key in ("source", "source_id", "title", "abstract", "authors",
                    "published", "journal", "categories", "doi", "url"):
            self.assertIn(key, d)

    def test_to_dict_returns_new_dict(self):
        p = Paper(source="pubmed", source_id="1", title="T")
        d1 = p.to_dict()
        d2 = p.to_dict()
        self.assertIsNot(d1, d2)


class TestCoerceDate(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_coerce_date(None))

    def test_date_object(self):
        self.assertEqual(_coerce_date(date(2024, 6, 15)), "2024-06-15")

    def test_datetime_object(self):
        self.assertEqual(_coerce_date(datetime(2023, 12, 1, 10, 30)), "2023-12-01")

    def test_iso_string_yyyymmdd(self):
        self.assertEqual(_coerce_date("2024-06-15"), "2024-06-15")

    def test_slash_separated(self):
        self.assertEqual(_coerce_date("2024/06/15"), "2024-06-15")

    def test_iso_with_time(self):
        self.assertEqual(_coerce_date("2024-06-15T00:00:00"), "2024-06-15")

    def test_year_month_string(self):
        # e.g. "2024 Jun"
        result = _coerce_date("2024 Jun")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("2024"))

    def test_year_only(self):
        result = _coerce_date("2024")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("2024"))

    def test_iso_prefix_fallback(self):
        # A long ISO-looking string should return first 10 chars
        result = _coerce_date("2024-06-15T12:00:00Z")
        self.assertEqual(result, "2024-06-15")

    def test_empty_string_none(self):
        # Empty string has no digit prefix → None
        self.assertIsNone(_coerce_date(""))

    def test_whitespace_string(self):
        self.assertIsNone(_coerce_date("  "))

    def test_year_month_day_string(self):
        result = _coerce_date("2023 Jan 15")
        self.assertEqual(result, "2023-01-15")


if __name__ == "__main__":
    unittest.main()
