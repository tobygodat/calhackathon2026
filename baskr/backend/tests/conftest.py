"""Shared fixtures and sys.path/sys.modules setup for Baskr backend tests."""

from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.models import (
    Classification,
    Label,
    PaperOut,
    Profile,
    ProfileItem,
    ProfileItemKind,
)

# ---------------------------------------------------------------------------
# Ensure system_pieces is importable (needed for ingest module imports)
# ---------------------------------------------------------------------------

_CALHACK_ROOT = Path(__file__).resolve().parents[4]  # calhackathon2026/
if str(_CALHACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_CALHACK_ROOT))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@pytest.fixture
def settings() -> Settings:
    """Settings with obviously-fake keys so no real API calls can succeed."""
    return Settings(
        openai_api_key="sk-test-openai",
        anthropic_api_key="sk-ant-test",
        redis_url="redis://localhost:6379",
        lab_id="test-lab",
        relevance_threshold=0.5,
        embed_model="text-embedding-3-small",
        reason_model="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_paper() -> PaperOut:
    return PaperOut(
        source="pubmed",
        source_id="12345",
        title="Gut Microbiome Modulation by Dietary Fiber",
        abstract=(
            "We investigated the role of dietary fiber in shaping gut microbiome "
            "composition and its downstream effects on host immune responses. "
            "Results showed a significant increase in Akkermansia muciniphila."
        ),
        authors=["Smith J", "Doe A"],
        doi="10.1234/test.doi",
        url="https://pubmed.ncbi.nlm.nih.gov/12345",
        journal="Nature Microbiology",
        published="2024-03-15",
        categories=["gut microbiome", "immunology"],
        uid="doi:10.1234/test.doi",
    )


@pytest.fixture
def sample_paper_no_abstract() -> PaperOut:
    return PaperOut(
        source="arxiv",
        source_id="2401.99999",
        title="A Paper Without Abstract",
        abstract="",
    )


@pytest.fixture
def sample_profile() -> Profile:
    return Profile(
        lab_id="test-lab",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=[
            ProfileItem(
                id="oq_1",
                kind=ProfileItemKind.OPEN_QUESTION,
                text="How does dietary fiber alter Akkermansia muciniphila abundance?",
            ),
            ProfileItem(
                id="asm_1",
                kind=ProfileItemKind.ASSUMPTION,
                text="Short-chain fatty acids mediate fiber-microbiome-immune crosstalk.",
            ),
            ProfileItem(
                id="fnd_1",
                kind=ProfileItemKind.FINDING,
                text="Inulin supplementation increased Bifidobacterium in our pilot cohort.",
            ),
        ],
    )


@pytest.fixture
def answers_classification() -> Classification:
    return Classification(
        label=Label.ANSWERS,
        reason="Paper directly addresses the open question about Akkermansia.",
        matched_item_id="oq_1",
        confidence=0.92,
    )


@pytest.fixture
def not_relevant_classification() -> Classification:
    return Classification(
        label=Label.NOT_RELEVANT,
        reason="Paper is about cardiac surgery with no microbiome connection.",
        matched_item_id=None,
        confidence=0.1,
    )
