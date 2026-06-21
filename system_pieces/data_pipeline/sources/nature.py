# ============================================================================
# WARNING: NATURE SOURCE IS DISABLED — DO NOT RE-ENABLE WITHOUT EXPLICIT REQUEST
# This entire file has been commented out. Do not uncomment or modify this code
# unless the user specifically asks to restore/fix the Nature source.
# ============================================================================

# """Nature source.
#
# Nature has no single free full-text API, so we use two paths:
#
#   1. Crossref (default, keyless) — filter works to Nature-portfolio ISSNs by
#      publication date + query. Returns metadata and, for many records, a JATS
#      abstract. This is the reliable, free path.
#
#   2. Springer Nature API (optional, SPRINGER_API_KEY) — richer abstracts/full
#      text for the Springer Nature portfolio. Used automatically when a key is
#      present.
#
# Crossref docs:        https://api.crossref.org/swagger-ui/index.html
# Springer Nature docs: https://dev.springernature.com/
# """
#
# from __future__ import annotations
#
# import re
# from datetime import date, timedelta
#
# from ..models import Paper, _coerce_date
# from .base import PaperSource
#
# CROSSREF_API = "https://api.crossref.org/works"
# SPRINGER_API = "https://api.springernature.com/meta/v2/json"
#
# # Nature flagship + a few high-volume portfolio journals (ISSNs).
# NATURE_ISSNS = [
#     "1476-4687",  # Nature (online)
#     "0028-0836",  # Nature (print)
#     "2041-1723",  # Nature Communications
#     "1546-170X",  # Nature Medicine
#     "1465-7392",  # Nature Cell Biology
#     "1078-8956",  # Nature Medicine (print)
# ]
#
# _TAG_RE = re.compile(r"<[^>]+>")
#
#
# def _strip_jats(text: str) -> str:
#     """Crossref abstracts are JATS XML; strip tags to plain text."""
#     if not text:
#         return ""
#     text = _TAG_RE.sub(" ", text)
#     return " ".join(text.split())
#
#
# class NatureSource(PaperSource):
#     name = "nature"
#
#     def __init__(self, config=None) -> None:
#         super().__init__(config) if config else super().__init__()
#         self._min_interval = 1.0
#
#     def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
#         if self.config.springer_api_key:
#             return self._fetch_springer(query, days=days, max_results=max_results)
#         return self._fetch_crossref(query, days=days, max_results=max_results)
#
#     # --- Crossref path (default, no key) ---
#     def _fetch_crossref(self, query: str, *, days: int, max_results: int) -> list[Paper]:
#         since = (date.today() - timedelta(days=days)).isoformat()
#         issn_filter = ",".join(f"issn:{i}" for i in NATURE_ISSNS)
#         params = {
#             "query": query,
#             "filter": f"from-online-pub-date:{since},{issn_filter}",
#             "rows": str(max_results),
#             "sort": "published",
#             "order": "desc",
#             "select": "DOI,title,author,abstract,container-title,published-online,published-print,URL,subject",
#             "mailto": self.config.contact_email,
#         }
#         items = self._get(CROSSREF_API, params=params).json().get("message", {}).get("items", [])
#         return [self._parse_crossref(it) for it in items]
#
#     def _parse_crossref(self, it: dict) -> Paper:
#         doi = (it.get("DOI") or "").strip() or None
#         title = " ".join(it.get("title") or []) if isinstance(it.get("title"), list) else (it.get("title") or "")
#         authors = [
#             f"{a.get('family', '')} {a.get('given', '')}".strip()
#             for a in it.get("author", [])
#         ]
#         date_parts = (
#             it.get("published-online", {}).get("date-parts")
#             or it.get("published-print", {}).get("date-parts")
#             or [[None]]
#         )[0]
#         published = "-".join(f"{p:02d}" if isinstance(p, int) else str(p) for p in date_parts if p)
#         journal = " ".join(it.get("container-title") or []) if isinstance(it.get("container-title"), list) else None
#
#         return Paper(
#             source=self.name,
#             source_id=doi or title,
#             title=title.strip(),
#             abstract=_strip_jats(it.get("abstract", "")),
#             authors=[a for a in authors if a],
#             doi=doi,
#             url=it.get("URL"),
#             journal=journal,
#             published=_coerce_date(published) or None,
#             categories=it.get("subject") or [],
#         )
#
#     # --- Springer Nature path (when SPRINGER_API_KEY is set) ---
#     def _fetch_springer(self, query: str, *, days: int, max_results: int) -> list[Paper]:
#         since = (date.today() - timedelta(days=days)).isoformat()
#         params = {
#             "q": f'{query} onlinedatefrom:{since}',
#             "p": str(max_results),
#             "api_key": self.config.springer_api_key,
#         }
#         records = self._get(SPRINGER_API, params=params).json().get("records", [])
#         return [self._parse_springer(r) for r in records]
#
#     def _parse_springer(self, r: dict) -> Paper:
#         doi = (r.get("doi") or "").strip() or None
#         creators = [c.get("creator", "").strip() for c in r.get("creators", [])]
#         url = next((u.get("value") for u in r.get("url", []) if u.get("value")), None)
#         return Paper(
#             source=self.name,
#             source_id=doi or r.get("title", ""),
#             title=(r.get("title") or "").strip(),
#             abstract=(r.get("abstract") or "").strip(),
#             authors=[c for c in creators if c],
#             doi=doi,
#             url=url or (f"https://doi.org/{doi}" if doi else None),
#             journal=r.get("publicationName"),
#             published=_coerce_date(r.get("onlineDate") or r.get("publicationDate")),
#             categories=[s.get("term") for s in r.get("subjects", []) if s.get("term")],
#         )
