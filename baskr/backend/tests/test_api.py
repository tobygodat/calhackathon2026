"""Integration tests for the SPEC §8 API routes via FastAPI TestClient.

Routes under test:
    GET  /api/profile
    POST /api/search
    GET  /api/digest/history
    GET  /api/digest/{date}
    POST /api/profile/memory
    POST /api/pipeline/search

All tests run keyless and without a live Redis server (modules are monkeypatched
so the tests are fast and fully offline).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Classification,
    Label,
    PaperOut,
    Profile,
    ProfileItem,
    ProfileItemKind,
    SearchHit,
)

client = TestClient(app)

# --- fixtures / helpers -------------------------------------------------------

_SAMPLE_PROFILE = Profile(
    lab_id="test-lab",
    niche="gut_microbiome",
    display_name="Test Lab",
    items=[
        ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION, text="How does fiber affect gut bacteria?"),
    ],
)

_SAMPLE_PAPER = PaperOut(
    source="pubmed",
    source_id="12345",
    title="Fiber and gut bacteria study",
    abstract="Dietary fiber significantly increases gut bacteria diversity.",
    authors=["Alice", "Bob"],
    published="2026-06-21",
    uid="pubmed:12345",
)

_SAMPLE_CLASSIFICATION = Classification(
    label=Label.VERIFIES,
    reason="Paper directly answers the profile question.",
    matched_item_id="oq_1",
    confidence=0.85,
)

_SAMPLE_HIT = SearchHit(paper=_SAMPLE_PAPER, classification=_SAMPLE_CLASSIFICATION)


# --- GET /api/profile ---------------------------------------------------------

def test_get_profile_returns_200_and_profile_shape(monkeypatch):
    monkeypatch.setattr("app.main.memory.load_profile", lambda s: _SAMPLE_PROFILE)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["lab_id"] == "test-lab"
    assert data["niche"] == "gut_microbiome"
    assert isinstance(data["items"], list)


# --- POST /api/search ---------------------------------------------------------

def test_post_search_returns_list_of_hits(monkeypatch):
    monkeypatch.setattr("app.main.engine.active_search", lambda q, s: [_SAMPLE_HIT])
    resp = client.post("/api/search", json={"question": "gut microbiome fiber"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["paper"]["title"] == _SAMPLE_PAPER.title
    assert data[0]["classification"]["label"] == "VERIFIES"


def test_post_search_returns_empty_for_no_hits(monkeypatch):
    monkeypatch.setattr("app.main.engine.active_search", lambda q, s: [])
    resp = client.post("/api/search", json={"question": "unrelated topic"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_post_search_requires_question():
    resp = client.post("/api/search", json={})
    assert resp.status_code == 422


# --- GET /api/digest/history --------------------------------------------------

def test_digest_history_returns_empty_list_when_no_digests(monkeypatch, tmp_path):
    monkeypatch.setattr("app.main._FROZEN_DIR", tmp_path)
    monkeypatch.setattr("app.main.get_client", lambda s: _MockRedisClient([]))
    resp = client.get("/api/digest/history")
    assert resp.status_code == 200
    assert resp.json() == []


def test_digest_history_with_filesystem_digest(monkeypatch, tmp_path):
    entries = [
        {
            "date": "2026-06-21",
            "paper": _SAMPLE_PAPER.model_dump(),
            "classification": _SAMPLE_CLASSIFICATION.model_dump(),
        }
    ]
    (tmp_path / "2026-06-21.json").write_text(json.dumps(entries))
    monkeypatch.setattr("app.main._FROZEN_DIR", tmp_path)
    monkeypatch.setattr("app.main.get_client", lambda s: _MockRedisClient([]))
    resp = client.get("/api/digest/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["date"] == "2026-06-21"
    assert data[0]["count"] == 1
    assert data[0]["top_label"] == "VERIFIES"


# --- GET /api/digest/{date} ---------------------------------------------------

def test_digest_for_date_reads_from_filesystem(monkeypatch, tmp_path):
    entries = [
        {
            "date": "2026-06-21",
            "paper": _SAMPLE_PAPER.model_dump(),
            "classification": _SAMPLE_CLASSIFICATION.model_dump(),
        }
    ]
    (tmp_path / "2026-06-21.json").write_text(json.dumps(entries))
    monkeypatch.setattr("app.main._FROZEN_DIR", tmp_path)
    monkeypatch.setattr("app.main.load_digest", lambda d, s: None)
    resp = client.get("/api/digest/2026-06-21")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["date"] == "2026-06-21"
    assert data[0]["paper"]["title"] == _SAMPLE_PAPER.title


def test_digest_for_date_returns_404_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("app.main._FROZEN_DIR", tmp_path)
    monkeypatch.setattr("app.main.load_digest", lambda d, s: None)
    resp = client.get("/api/digest/1999-01-01")
    assert resp.status_code == 404


# --- POST /api/profile/memory -------------------------------------------------

def test_add_memory_returns_updated_profile(monkeypatch):
    updated = Profile(
        lab_id="test-lab",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=[
            ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION, text="How does fiber affect gut bacteria?"),
            ProfileItem(id="fnd_1", kind=ProfileItemKind.FINDING, text="Fiber increases diversity."),
        ],
    )
    monkeypatch.setattr("app.main.memory.append_item", lambda k, t, s: updated)
    resp = client.post(
        "/api/profile/memory",
        json={"kind": "finding", "text": "Fiber increases diversity."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2


# --- POST /api/pipeline/search ------------------------------------------------

def test_pipeline_search_returns_papers_counts_errors(monkeypatch):
    papers = [_SAMPLE_PAPER]
    counts = {"pubmed": 1}
    errors: dict = {}
    monkeypatch.setattr("app.main.fetch_raw", lambda q, d, m, s: (papers, counts, errors))
    resp = client.post("/api/pipeline/search", json={"query": "gut microbiome"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["papers"], list)
    assert len(data["papers"]) == 1
    assert isinstance(data["counts"], dict)
    assert isinstance(data["errors"], dict)


def test_pipeline_search_filters_by_source(monkeypatch):
    arxiv_paper = _SAMPLE_PAPER.model_copy(update={"source": "arxiv"})
    papers = [_SAMPLE_PAPER, arxiv_paper]
    monkeypatch.setattr(
        "app.main.fetch_raw",
        lambda q, d, m, s: (papers, {"pubmed": 1, "arxiv": 1}, {}),
    )
    resp = client.post(
        "/api/pipeline/search",
        json={"query": "gut microbiome", "sources": ["pubmed"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["source"] == "pubmed" for p in data["papers"])


# --- helper: minimal Redis client mock ----------------------------------------

class _MockRedisClient:
    """Minimal mock that returns no keys for SCAN/KEYS."""

    def __init__(self, keys: list[bytes]) -> None:
        self._keys = keys

    def keys(self, pattern: str) -> list[bytes]:
        return self._keys
