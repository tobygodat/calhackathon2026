"""bioRxiv (and medRxiv) source via the public details API. No API key required.

The bioRxiv API is date-range based, not keyword based: you pull every preprint
posted in a window, then filter locally. That's a good fit for the daily-digest
use case ("everything new today"), and we apply a lightweight keyword filter so
active-search behaves like the other sources.

Docs: https://api.biorxiv.org/
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import Paper, _coerce_date
from .base import PaperSource

BIORXIV_API = "https://api.biorxiv.org/details"


class BioRxivSource(PaperSource):
    name = "biorxiv"

    def __init__(self, config=None, server: str = "biorxiv") -> None:
        super().__init__(config) if config else super().__init__()
        self.server = server  # "biorxiv" or "medrxiv"
        self._min_interval = 1.0

    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        end = date.today()
        start = end - timedelta(days=days)
        terms = [t.lower() for t in query.split() if len(t) > 2]

        papers: list[Paper] = []
        cursor = 0
        while len(papers) < max_results:
            batch = self._fetch_page(start, end, cursor)
            if not batch:
                break
            for item in batch:
                paper = self._parse_item(item)
                if self._matches(paper, terms):
                    papers.append(paper)
                    if len(papers) >= max_results:
                        break
            cursor += len(batch)
            if len(batch) < 100:  # API returns up to 100 per page
                break
        return papers

    def _fetch_page(self, start: date, end: date, cursor: int) -> list[dict]:
        url = f"{BIORXIV_API}/{self.server}/{start.isoformat()}/{end.isoformat()}/{cursor}"
        data = self._get(url).json()
        return data.get("collection", [])

    @staticmethod
    def _matches(paper: Paper, terms: list[str]) -> bool:
        if not terms:
            return True
        haystack = f"{paper.title} {paper.abstract} {' '.join(paper.categories)}".lower()
        return any(term in haystack for term in terms)

    def _parse_item(self, item: dict) -> Paper:
        doi = (item.get("doi") or "").strip() or None
        authors = [a.strip() for a in (item.get("authors") or "").split(";") if a.strip()]
        return Paper(
            source=self.name,
            source_id=doi or item.get("title", ""),
            title=(item.get("title") or "").strip(),
            abstract=(item.get("abstract") or "").strip(),
            authors=authors,
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else None,
            journal=self.server,
            published=_coerce_date(item.get("date")),
            categories=[item["category"]] if item.get("category") else [],
            raw={"version": item.get("version"), "server": self.server},
        )
