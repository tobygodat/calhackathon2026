"""ChemRxiv source via the Cambridge Open Engage public API. No API key required.

ChemRxiv is the preprint server for chemistry. The public API has no clean
keyword + date-range combo, so we fetch recent items sorted by date and filter
client-side by the requested `days` window (same strategy as arXiv).

Docs: https://chemrxiv.org/engage/chemrxiv/public-api/documentation
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..models import Paper, _coerce_date
from .base import PaperSource

CHEMRXIV_BASE = "https://chemrxiv.org/engage/chemrxiv/public-api/v1"


def _strip_doi(value: str | None) -> str | None:
    """Return the bare, lowercased DOI (no https://doi.org/ prefix)."""
    if not value:
        return None
    doi = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    doi = doi.strip().lower()
    return doi or None


class ChemRxivSource(PaperSource):
    name = "chemrxiv"

    def __init__(self, config=None) -> None:
        super().__init__(config) if config else super().__init__()
        self._min_interval = 1.0

    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        params = {
            "term": query,
            "limit": min(max_results, 50),
            "skip": 0,
            "sort": "PUBLISHED_DATE_DESC",
        }
        data = self._get(f"{CHEMRXIV_BASE}/items", params=params).json()
        hits = (data or {}).get("itemHits") or []

        cutoff = date.today() - timedelta(days=days)
        papers: list[Paper] = []
        for hit in hits:
            item = self._extract_item(hit)
            if not item:
                continue
            paper = self._parse_item(item)
            pub = self._published_date(paper.published)
            if pub is not None and pub < cutoff:
                continue
            papers.append(paper)
            if len(papers) >= max_results:
                break
        return papers

    # --- helpers (unit-testable in isolation) ---
    @staticmethod
    def _extract_item(hit: dict) -> dict:
        """Pull the inner item dict from a search hit.

        Handles both `{"item": {...}}` and a bare item dict.
        """
        if not isinstance(hit, dict):
            return {}
        inner = hit.get("item")
        if isinstance(inner, dict):
            return inner
        return hit

    @staticmethod
    def _published_date(value: str | None) -> date | None:
        """Parse a YYYY-MM-DD string (from _coerce_date) into a date."""
        if not value:
            return None
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _parse_item(self, item: dict) -> Paper:
        """Map an inner ChemRxiv item dict onto a normalized Paper."""
        item = item or {}

        source_id = str(item.get("id") or "")
        title = " ".join((item.get("title") or "").split())
        abstract = " ".join((item.get("abstract") or "").split())

        doi = _strip_doi(item.get("doi"))

        authors: list[str] = []
        for a in item.get("authors") or []:
            if not isinstance(a, dict):
                continue
            full = f'{a.get("firstName", "")} {a.get("lastName", "")}'.strip()
            if full:
                authors.append(full)

        published = _coerce_date(
            item.get("publishedDate")
            or item.get("statusDate")
            or item.get("submittedDate")
        )

        if doi:
            url = f"https://doi.org/{doi}"
        else:
            url = item.get("asset", {}).get("original", {}).get("url") if isinstance(item.get("asset"), dict) else None
            url = url or None

        categories = [
            c.get("name")
            for c in (item.get("categories") or [])
            if isinstance(c, dict) and c.get("name")
        ]

        return Paper(
            source=self.name,
            source_id=source_id,
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            url=url,
            journal="ChemRxiv",
            published=published,
            categories=categories,
            raw={"chemrxiv_id": source_id},
        )
