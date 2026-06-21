"""Pydantic data contracts for the API and storage layers (SPEC §5).

Note on ``Paper``: Baskr reuses the normalized paper shape produced by
``implementations/data_pipeline`` (``DataPipeline`` -> ``Paper.to_dict()``) rather
than the PMID-only shape sketched in SPEC §5.2. ``PaperOut`` below mirrors that
dict so the engine, API, and frontend all speak the same multi-source schema.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# --- enums -----------------------------------------------------------------

class ProfileItemKind(str, Enum):
    OPEN_QUESTION = "open_question"
    ASSUMPTION = "assumption"
    FINDING = "finding"
    PLANNED_EXPERIMENT = "planned_experiment"  # required only for SCOOP (stretch)


class Label(str, Enum):
    VERIFIES = "VERIFIES"
    CONTRADICTS = "CONTRADICTS"
    EXTENDS = "EXTENDS"
    TANGENTIAL = "TANGENTIAL"
    SCOOP = "SCOOP"  # stretch label, only with planned_experiment items


# Sort priority for relationship labels — lower rank = surfaced first (SPEC §6).
# CONTRADICTS -> VERIFIES -> EXTENDS -> TANGENTIAL, with the stretch SCOOP label
# slotted just after CONTRADICTS. Single source of truth for engine._sort_hits.
_LABEL_ORDER: tuple[Label, ...] = (
    Label.CONTRADICTS,
    Label.SCOOP,
    Label.VERIFIES,
    Label.EXTENDS,
    Label.TANGENTIAL,
)
LABEL_PRIORITY: dict[Label, int] = {label: i for i, label in enumerate(_LABEL_ORDER)}


def label_rank(label: Label) -> int:
    """Sort rank for ``label`` (lower = higher priority); unknown labels sort last."""
    return LABEL_PRIORITY.get(label, len(_LABEL_ORDER))


# --- profile (SPEC §5.1) ----------------------------------------------------

class ProfileItem(BaseModel):
    id: str
    kind: ProfileItemKind
    text: str


class Profile(BaseModel):
    lab_id: str
    niche: str
    display_name: str
    items: list[ProfileItem] = Field(default_factory=list)


# --- paper (mirrors data_pipeline Paper.to_dict()) --------------------------

class PaperOut(BaseModel):
    source: str          # "pubmed" | "arxiv" | "biorxiv" | "nature"
    source_id: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    url: str | None = None
    journal: str | None = None
    published: str | None = None     # ISO YYYY-MM-DD
    categories: list[str] = Field(default_factory=list)
    uid: str | None = None           # stable cross-source id from Paper.uid


# --- classification (SPEC §5.3) ---------------------------------------------

class Classification(BaseModel):
    label: Label
    reason: str
    matched_item_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


# --- digest (SPEC §5.4) -----------------------------------------------------

class DigestEntry(BaseModel):
    date: str                       # YYYY-MM-DD
    paper: PaperOut                 # paper minus embedding
    classification: Classification


class DigestSummary(BaseModel):
    """One row of /api/digest/history."""
    date: str
    count: int
    top_label: Label


# --- request/response bodies (SPEC §8) --------------------------------------

class SearchRequest(BaseModel):
    question: str


class SearchHit(BaseModel):
    paper: PaperOut
    classification: Classification


class MemoryWriteRequest(BaseModel):
    """POST /api/profile/memory (stretch)."""
    kind: ProfileItemKind
    text: str


class PipelineSearchRequest(BaseModel):
    """POST /api/pipeline/search — dev UI pipeline panel."""
    query: str
    days: int = 7
    sources: list[str] | None = None
    max_results: int = 50


class PipelineSearchResult(BaseModel):
    """Response shape for POST /api/pipeline/search."""
    papers: list[PaperOut]
    errors: dict[str, str] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
