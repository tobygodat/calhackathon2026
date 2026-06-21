"""Integration tests for the FastAPI routes (app/main.py).

Routes use lazy imports. We patch at the SOURCE modules:
  - app.memory.load_profile     (get_profile, add_memory routes)
  - app.engine.active_search    (search route)
  - app.memory.append_item      (add_memory route)
  - app.main._DIGEST_DIR        (digest history/date routes read JSON files)
  - app.redis_client.load_digest (digest/{date} fallback)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Classification,
    Label,
    MemoryWriteRequest,
    PaperOut,
    Profile,
    ProfileItem,
    ProfileItemKind,
    SearchHit,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile() -> Profile:
    return Profile(
        lab_id="test-lab",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=[
            ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                        text="How does fiber affect microbiome?"),
        ],
    )


def _make_search_hit(label: Label = Label.ANSWERS,
                     confidence: float = 0.85) -> SearchHit:
    paper = PaperOut(
        source="pubmed",
        source_id="99999",
        title="Fiber and Akkermansia",
        abstract="We studied fiber effects on Akkermansia.",
        authors=["Smith J"],
        published="2024-03-15",
    )
    classification = Classification(
        label=label,
        reason="Directly addresses the open question.",
        matched_item_id="oq_1",
        confidence=confidence,
    )
    return SearchHit(paper=paper, classification=classification)


def _digest_entry(source_id: str = "1", label: str = "ANSWERS") -> dict:
    return {
        "date": "2024-03-15",
        "paper": {
            "source": "pubmed", "source_id": source_id,
            "title": f"Paper {source_id}", "abstract": "Abstract.",
            "authors": ["A"], "doi": None, "url": None,
            "journal": None, "published": "2024-03-15",
            "categories": [], "uid": None,
        },
        "classification": {
            "label": label, "reason": "r",
            "matched_item_id": None, "confidence": 0.8,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

class TestHealthRoute:
    def test_returns_200(self, client):
        assert client.get("/api/health").status_code == 200

    def test_returns_ok(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /api/profile
# ---------------------------------------------------------------------------

class TestProfileRoute:
    def test_returns_200(self, client):
        with patch("app.memory.load_profile", return_value=_make_profile()):
            assert client.get("/api/profile").status_code == 200

    def test_response_has_required_keys(self, client):
        with patch("app.memory.load_profile", return_value=_make_profile()):
            data = client.get("/api/profile").json()
        assert {"lab_id", "display_name", "items"}.issubset(data)

    def test_returns_profile_data(self, client):
        with patch("app.memory.load_profile", return_value=_make_profile()):
            data = client.get("/api/profile").json()
        assert data["lab_id"] == "test-lab"
        assert data["display_name"] == "Test Lab"
        assert len(data["items"]) == 1

    def test_item_has_id_kind_text(self, client):
        with patch("app.memory.load_profile", return_value=_make_profile()):
            item = client.get("/api/profile").json()["items"][0]
        assert {"id", "kind", "text"}.issubset(item)


# ---------------------------------------------------------------------------
# POST /api/search
# ---------------------------------------------------------------------------

class TestSearchRoute:
    def test_returns_200(self, client):
        with patch("app.engine.active_search", return_value=[_make_search_hit()]):
            assert client.post("/api/search",
                               json={"question": "fiber"}).status_code == 200

    def test_returns_list(self, client):
        with patch("app.engine.active_search", return_value=[_make_search_hit()]):
            data = client.post("/api/search", json={"question": "q"}).json()
        assert isinstance(data, list)

    def test_hit_has_paper_and_classification(self, client):
        with patch("app.engine.active_search", return_value=[_make_search_hit()]):
            item = client.post("/api/search", json={"question": "q"}).json()[0]
        assert "paper" in item
        assert "classification" in item

    def test_classification_label_and_confidence(self, client):
        hit = _make_search_hit(Label.EXTENDS, 0.72)
        with patch("app.engine.active_search", return_value=[hit]):
            cl = client.post("/api/search",
                             json={"question": "q"}).json()[0]["classification"]
        assert cl["label"] == "EXTENDS"
        assert cl["confidence"] == pytest.approx(0.72)

    def test_empty_results(self, client):
        with patch("app.engine.active_search", return_value=[]):
            data = client.post("/api/search", json={"question": "q"}).json()
        assert data == []

    def test_missing_question_returns_422(self, client):
        assert client.post("/api/search", json={}).status_code == 422

    def test_engine_error_returns_500(self, client):
        with patch("app.engine.active_search",
                   side_effect=RuntimeError("API down")):
            assert client.post("/api/search",
                               json={"question": "q"}).status_code == 500

    def test_question_forwarded_to_engine(self, client):
        captured = []
        with patch("app.engine.active_search",
                   side_effect=lambda q: captured.append(q) or []):
            client.post("/api/search", json={"question": "fiber microbiome"})
        assert captured == ["fiber microbiome"]

    def test_paper_source_field_present(self, client):
        with patch("app.engine.active_search", return_value=[_make_search_hit()]):
            paper = client.post("/api/search",
                                json={"question": "q"}).json()[0]["paper"]
        assert "source" in paper


# ---------------------------------------------------------------------------
# GET /api/digest/history
# ---------------------------------------------------------------------------

class TestDigestHistoryRoute:
    def test_returns_200(self, client, tmp_path):
        with patch("app.main._DIGEST_DIR", tmp_path):
            assert client.get("/api/digest/history").status_code == 200

    def test_returns_list(self, client, tmp_path):
        with patch("app.main._DIGEST_DIR", tmp_path):
            assert isinstance(client.get("/api/digest/history").json(), list)

    def test_empty_when_no_files(self, client, tmp_path):
        with patch("app.main._DIGEST_DIR", tmp_path):
            assert client.get("/api/digest/history").json() == []

    def test_one_summary_per_digest_file(self, client, tmp_path):
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps([_digest_entry()]), encoding="utf-8")
        (tmp_path / "2024-03-14.json").write_text(
            json.dumps([_digest_entry()]), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            data = client.get("/api/digest/history").json()
        assert len(data) == 2

    def test_summary_fields(self, client, tmp_path):
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps([_digest_entry()]), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            summary = client.get("/api/digest/history").json()[0]
        assert {"date", "count", "top_label"}.issubset(summary)

    def test_count_matches_entries(self, client, tmp_path):
        entries = [_digest_entry(str(i)) for i in range(3)]
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps(entries), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            summary = client.get("/api/digest/history").json()[0]
        assert summary["count"] == 3

    def test_top_label_is_most_common(self, client, tmp_path):
        entries = [
            _digest_entry("1", "EXTENDS"),
            _digest_entry("2", "EXTENDS"),
            _digest_entry("3", "ANSWERS"),
        ]
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps(entries), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            summary = client.get("/api/digest/history").json()[0]
        assert summary["top_label"] == "EXTENDS"


# ---------------------------------------------------------------------------
# GET /api/digest/{date}
# ---------------------------------------------------------------------------

class TestDigestForDateRoute:
    def test_returns_200_for_existing_file(self, client, tmp_path):
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps([_digest_entry()]), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            assert client.get("/api/digest/2024-03-15").status_code == 200

    def test_returns_entries_list(self, client, tmp_path):
        entries = [_digest_entry("1"), _digest_entry("2")]
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps(entries), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            data = client.get("/api/digest/2024-03-15").json()
        assert len(data) == 2

    def test_entry_has_paper_and_classification(self, client, tmp_path):
        (tmp_path / "2024-03-15.json").write_text(
            json.dumps([_digest_entry()]), encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            entry = client.get("/api/digest/2024-03-15").json()[0]
        assert "paper" in entry
        assert "classification" in entry

    def test_returns_404_for_missing_date(self, client, tmp_path):
        with patch("app.main._DIGEST_DIR", tmp_path):
            with patch("app.redis_client.load_digest", return_value=None):
                resp = client.get("/api/digest/9999-01-01")
        assert resp.status_code == 404

    def test_empty_file_returns_empty_list(self, client, tmp_path):
        (tmp_path / "2024-03-15.json").write_text("[]", encoding="utf-8")
        with patch("app.main._DIGEST_DIR", tmp_path):
            assert client.get("/api/digest/2024-03-15").json() == []


# ---------------------------------------------------------------------------
# POST /api/profile/memory  (stretch)
# ---------------------------------------------------------------------------

class TestAddMemoryRoute:
    def test_returns_200(self, client):
        updated = _make_profile()
        updated.items.append(
            ProfileItem(id="fnd_1", kind=ProfileItemKind.FINDING,
                        text="New finding."))
        with patch("app.memory.append_item", return_value=updated):
            resp = client.post("/api/profile/memory",
                               json={"kind": "finding", "text": "New finding."})
        assert resp.status_code == 200

    def test_returns_profile_with_new_item(self, client):
        updated = _make_profile()
        updated.items.append(
            ProfileItem(id="fnd_1", kind=ProfileItemKind.FINDING,
                        text="New finding."))
        with patch("app.memory.append_item", return_value=updated):
            data = client.post(
                "/api/profile/memory",
                json={"kind": "finding", "text": "New finding."},
            ).json()
        assert len(data["items"]) == 2

    def test_missing_body_returns_422(self, client):
        assert client.post("/api/profile/memory", json={}).status_code == 422

    def test_invalid_kind_returns_422(self, client):
        assert client.post(
            "/api/profile/memory",
            json={"kind": "not_a_kind", "text": "text"},
        ).status_code == 422

    def test_kind_and_text_forwarded(self, client):
        captured = {}

        def capture(kind, text):
            captured.update({"kind": kind, "text": text})
            return _make_profile()

        with patch("app.memory.append_item", side_effect=capture):
            client.post("/api/profile/memory",
                        json={"kind": "assumption", "text": "We assume X."})
        assert captured["kind"] == ProfileItemKind.ASSUMPTION
        assert captured["text"] == "We assume X."
