"""PubMed source via NCBI E-utilities (esearch + efetch).

Free, no paywall, returns full abstracts. An NCBI API key is optional and only
raises the rate limit (3 -> 10 req/sec); the adapter works without one.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..models import Paper, _coerce_date
from .base import PaperSource

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedSource(PaperSource):
    name = "pubmed"

    def __init__(self, config=None) -> None:
        super().__init__(config) if config else super().__init__()
        # honor NCBI's per-second cap with a touch of headroom
        self._min_interval = 1.0 / self.config.ncbi_rate_limit

    def _common_params(self) -> dict[str, str]:
        params = {"db": "pubmed", "tool": self.config.tool_name, "email": self.config.contact_email}
        if self.config.ncbi_api_key:
            params["api_key"] = self.config.ncbi_api_key
        return params

    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        pmids = self._search(query, days=days, max_results=max_results)
        if not pmids:
            return []
        return self._fetch_details(pmids)

    def _search(self, query: str, *, days: int, max_results: int) -> list[str]:
        params = self._common_params() | {
            "term": query,
            "retmax": str(max_results),
            "retmode": "json",
            "datetype": "edat",      # Entrez date = when it appeared in PubMed
            "reldate": str(days),    # within the last N days
            "sort": "date",
        }
        data = self._get(f"{EUTILS}/esearch.fcgi", params=params).json()
        return data.get("esearchresult", {}).get("idlist", [])

    def _fetch_details(self, pmids: list[str]) -> list[Paper]:
        params = self._common_params() | {"id": ",".join(pmids), "retmode": "xml"}
        xml = self._get(f"{EUTILS}/efetch.fcgi", params=params).text
        root = ET.fromstring(xml)

        papers: list[Paper] = []
        for art in root.findall(".//PubmedArticle"):
            papers.append(self._parse_article(art))
        return papers

    @staticmethod
    def _text(node, path: str, default: str = "") -> str:
        found = node.find(path)
        return (found.text or default).strip() if found is not None and found.text else default

    def _parse_article(self, art: ET.Element) -> Paper:
        pmid = self._text(art, ".//PMID")
        title = self._text(art, ".//ArticleTitle")

        # Abstracts can be split into labeled sections (BACKGROUND, METHODS...)
        abstract_parts: list[str] = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            txt = "".join(ab.itertext()).strip()
            if not txt:
                continue
            abstract_parts.append(f"{label}: {txt}" if label else txt)
        abstract = "\n".join(abstract_parts)

        authors: list[str] = []
        for a in art.findall(".//AuthorList/Author"):
            last = self._text(a, "LastName")
            initials = self._text(a, "Initials")
            collective = self._text(a, "CollectiveName")
            if last:
                authors.append(f"{last} {initials}".strip())
            elif collective:
                authors.append(collective)

        journal = self._text(art, ".//Journal/Title")
        doi = None
        for idn in art.findall(".//ArticleIdList/ArticleId"):
            if idn.get("IdType") == "doi" and idn.text:
                doi = idn.text.strip()
                break

        # publication date — prefer the article date, fall back to journal issue
        y = self._text(art, ".//PubDate/Year") or self._text(art, ".//ArticleDate/Year")
        m = self._text(art, ".//PubDate/Month") or self._text(art, ".//ArticleDate/Month") or "01"
        d = self._text(art, ".//PubDate/Day") or self._text(art, ".//ArticleDate/Day") or "01"
        published = _coerce_date(f"{y} {m} {d}".strip()) if y else None

        return Paper(
            source=self.name,
            source_id=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            journal=journal or None,
            published=published,
            categories=[mh.text for mh in art.findall(".//MeshHeading/DescriptorName") if mh.text],
        )
