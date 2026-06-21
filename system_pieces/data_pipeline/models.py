"""Normalized data model shared across every paper source.

Every source adapter (PubMed, arXiv, bioRxiv) maps its native
response onto a single `Paper` shape so the downstream engine — embedding +
Redis vector search + the Claude classify prompt — never has to care where a
paper came from.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any


@dataclass
class Paper:
    """A single research paper, normalized across all sources."""

    # --- identity ---
    source: str                 # "pubmed" | "arxiv" | "biorxiv"
    source_id: str              # PMID, arXiv id, DOI, etc. (unique within source)
    title: str

    # --- content the engine reasons over ---
    abstract: str = ""
    authors: list[str] = field(default_factory=list)

    # --- provenance / display ---
    doi: str | None = None
    url: str | None = None
    journal: str | None = None
    published: str | None = None      # ISO date string (YYYY-MM-DD) when known
    categories: list[str] = field(default_factory=list)

    # raw payload kept for debugging / future fields, never sent to the model
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def uid(self) -> str:
        """Stable global id. Prefer DOI (dedupes the same paper across
        sources, e.g. a bioRxiv preprint later published in a journal)."""
        if self.doi:
            return f"doi:{self.doi.lower()}"
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Hash of normalized title — last-resort dedupe when DOIs differ."""
        norm = "".join(ch for ch in self.title.lower() if ch.isalnum())
        return hashlib.sha1(norm.encode()).hexdigest()

    @property
    def has_abstract(self) -> bool:
        return bool(self.abstract and self.abstract.strip())

    def citation(self) -> str:
        """Short human-readable citation for the UI / digest."""
        first_author = self.authors[0] if self.authors else "Unknown"
        et_al = " et al." if len(self.authors) > 1 else ""
        venue = self.journal or self.source.capitalize()
        year = (self.published or "")[:4]
        return f"{first_author}{et_al} ({year}). {self.title}. {venue}."

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["uid"] = self.uid
        return d


def _coerce_date(value: Any) -> str | None:
    """Best-effort normalization of assorted date shapes to YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y %b %d", "%Y %b", "%Y"):
            try:
                return datetime.strptime(value[: len(fmt) + 4], fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # already looks like an ISO prefix
        if len(value) >= 4 and value[:4].isdigit():
            return value[:10]
    return None
