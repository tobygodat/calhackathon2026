"""arXiv source via the public Atom API. No API key required.

Most relevant categories for a bio/health lab: q-bio.* (quantitative biology).
Docs: https://info.arxiv.org/help/api/user-manual.html
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from ..models import Paper, _coerce_date
from .base import PaperSource

ARXIV_API = "http://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"


class ArxivSource(PaperSource):
    name = "arxiv"

    def __init__(self, config=None) -> None:
        super().__init__(config) if config else super().__init__()
        # arXiv asks callers to keep to ~1 request / 3s
        self._min_interval = 3.0

    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        # arXiv has no reliable server-side date filter in search_query, so we
        # over-fetch sorted by submission date and filter client-side.
        params = {
            "search_query": query,
            "start": "0",
            "max_results": str(max_results * 3),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        xml = self._get(ARXIV_API, params=params).text
        root = ET.fromstring(xml)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        papers: list[Paper] = []
        for entry in root.findall(f"{ATOM}entry"):
            paper = self._parse_entry(entry)
            pub = paper.raw.get("_published_dt")
            if pub and pub < cutoff:
                continue
            papers.append(paper)
            if len(papers) >= max_results:
                break
        return papers

    def _parse_entry(self, entry: ET.Element) -> Paper:
        def text(tag: str) -> str:
            node = entry.find(f"{ATOM}{tag}")
            return (node.text or "").strip() if node is not None else ""

        arxiv_url = text("id")               # e.g. http://arxiv.org/abs/2406.12345v1
        arxiv_id = arxiv_url.rsplit("/", 1)[-1] if arxiv_url else ""
        published_raw = text("published")    # ISO 8601 w/ Z
        published_dt = None
        if published_raw:
            try:
                published_dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                published_dt = None

        authors = [
            (a.find(f"{ATOM}name").text or "").strip()
            for a in entry.findall(f"{ATOM}author")
            if a.find(f"{ATOM}name") is not None
        ]
        categories = [
            c.get("term") for c in entry.findall(f"{ATOM}category") if c.get("term")
        ]
        doi_node = entry.find("{http://arxiv.org/schemas/atom}doi")
        doi = (doi_node.text or "").strip() if doi_node is not None else None

        return Paper(
            source=self.name,
            source_id=arxiv_id,
            title=" ".join(text("title").split()),
            abstract=" ".join(text("summary").split()),
            authors=authors,
            doi=doi,
            url=arxiv_url or None,
            journal="arXiv",
            published=_coerce_date(published_raw),
            categories=categories,
            raw={"_published_dt": published_dt},
        )
