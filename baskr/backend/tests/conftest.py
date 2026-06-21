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
# Monitoring isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_monitoring(tmp_path_factory, monkeypatch):
    """Repoint the monitoring CSV logs at a throwaway dir and reset in-memory
    state, so /status / pipeline tests never touch the real data/ CSVs."""
    import app.monitoring as mon

    d = tmp_path_factory.mktemp("monitoring")
    monkeypatch.setattr(mon, "NEW_PAPERS_CSV", d / "new_papers_seen.csv")
    monkeypatch.setattr(mon, "STATUS_LOG_CSV", d / "service_status_log.csv")
    mon.reset_state()
    yield
    mon.reset_state()


# ---------------------------------------------------------------------------
# Embeddings isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _offline_external_services(monkeypatch):
    """Keep the whole suite offline/deterministic despite real keys in ``.env``.

    ``Settings()`` now picks up a real ``OPENAI_API_KEY`` and the ``AGENT_MEMORY_*``
    Iris credentials are in the environment, so without this any test that flows
    into ``embed_text``/``embed_batch`` (engine pre-filter, memory semantic rank,
    ingest) or ``memory.retrieve_relevant`` (Iris LTM recall) would make a real
    network call. Patching the two single chokepoints forces the local keyless /
    local-memory paths regardless of how a test constructs ``Settings``."""
    monkeypatch.setattr("app.embeddings._should_use_openai", lambda *a, **k: False)
    monkeypatch.setattr("app.agent_memory.is_enabled", lambda *a, **k: False)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@pytest.fixture
def settings() -> Settings:
    """Settings with obviously-fake keys so no real API calls can succeed."""
    return Settings(
        anthropic_api_key="sk-ant-test",
        openai_api_key=None,
        redis_url="redis://localhost:6379",
        lab_id="test-lab",
        relevance_threshold=0.5,
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


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Yield a FastAPI TestClient for the app (imported lazily)."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
