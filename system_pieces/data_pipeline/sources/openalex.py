"""OpenAlex source via the public works API. No API key required.

OpenAlex provides a free, open catalog of scholarly works. Supplying a
contact email (`mailto`) opts into the faster "polite pool".
Docs: https://docs.openalex.org/api-entities/works
"""

from __future__ import annotations

from datetime import date, timedelta

from ..models import Paper, _coerce_date
from .base import PaperSource

OPENALEX_API = "https://api.openalex.org/works"


class OpenAlexSource(PaperSource):
    name = "openalex"

    def __init__(self, config=None) -> None:
        super().__init__(config) if config else super().__init__()
        # OpenAlex polite pool allows generous rates; keep a small interval.
        self._min_interval = 0.1

    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        from_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        params = {
            "search": query,
            "filter": f"from_publication_date:{from_date}",
            "sort": "publication_date:desc",
            "per_page": str(min(max_results, 200)),
            "mailto": self.config.contact_email,
        }
        data = self._get(OPENALEX_API, params=params).json()
        results = data.get("results") or []

        papers: list[Paper] = []
        for item in results:
            papers.append(self._parse_item(item))
            if len(papers) >= max_results:
                break
        return papers

    # --- helpers ---
    def _reconstruct_abstract(self, inv_index) -> str:
        """Rebuild plain-text abstract from OpenAlex's inverted index.

        `inv_index` maps each word to a list of positions it occupies.
        """
        if not inv_index:
            return ""
        positions: list[tuple[int, str]] = []
        for word, idxs in inv_index.items():
            for pos in idxs or []:
                positions.append((pos, word))
        positions.sort(key=lambda p: p[0])
        return " ".join(word for _, word in positions)

    def _parse_item(self, item: dict) -> Paper:
        # --- identity ---
        oa_id = item.get("id") or ""
        source_id = oa_id.rsplit("/", 1)[-1] if oa_id else ""

        title = item.get("title") or item.get("display_name") or ""

        # --- doi (bare, lowercased) ---
        doi_raw = item.get("doi")
        doi = None
        if doi_raw:
            doi = doi_raw.strip()
            for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
                if doi.lower().startswith(prefix):
                    doi = doi[len(prefix):]
                    break
            doi = doi.lower() or None

        # --- abstract ---
        abstract = self._reconstruct_abstract(item.get("abstract_inverted_index"))

        # --- authors ---
        authors: list[str] = []
        for a in item.get("authorships") or []:
            try:
                name = (a.get("author") or {}).get("display_name")
                if name:
                    authors.append(name)
            except (AttributeError, TypeError):
                continue

        # --- journal (deeply nullable) ---
        journal = None
        primary = item.get("primary_location") or {}
        try:
            src = primary.get("source") or {}
            journal = src.get("display_name")
        except (AttributeError, TypeError):
            journal = None

        # --- url ---
        landing = None
        try:
            landing = primary.get("landing_page_url")
        except (AttributeError, TypeError):
            landing = None
        if doi:
            url = f"https://doi.org/{doi}"
        elif landing:
            url = landing
        else:
            url = oa_id or None

        # --- categories ---
        categories: list[str] = []
        for c in item.get("concepts") or []:
            try:
                name = c.get("display_name")
                if name:
                    categories.append(name)
            except (AttributeError, TypeError):
                continue

        return Paper(
            source=self.name,
            source_id=source_id,
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            url=url,
            journal=journal,
            published=_coerce_date(item.get("publication_date")),
            categories=categories,
            raw={"openalex_id": oa_id},
        )
