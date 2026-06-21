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


# ---------------------------------------------------------------------------
# GET /status  (dev-ui monitor)
# ---------------------------------------------------------------------------

class TestStatusRoute:
    """/status makes live network probes; patch ThreadPoolExecutor so the probes
    return a deterministic, all-healthy result without touching the network."""

    def _patch_probes(self, results: dict):
        """Patch app.main._probe to return canned results keyed by probe fn name."""
        import app.main as main

        def fake_probe(fn):
            return results.get(fn.__name__, {"ok": True, "latency_ms": 1.0})

        return patch.object(main, "_probe", side_effect=fake_probe)

    def test_returns_expected_shape(self, client, tmp_path):
        with self._patch_probes({}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        assert {"healthy", "connections", "metrics", "redis_sources"}.issubset(data)
        # Exactly the seven services the dev-ui renders are probed (no openai).
        assert set(data["connections"]) == {
            "pubmed", "arxiv", "biorxiv", "redis", "redisvl",
            "anthropic", "consumer",
        }
        assert "openai" not in data["connections"]

    def test_metrics_include_new_papers_seen(self, client, tmp_path):
        with self._patch_probes({}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        assert "new_papers_seen" in data["metrics"]
        assert isinstance(data["metrics"]["new_papers_seen"], int)

    def test_healthy_true_when_all_ok(self, client, tmp_path):
        with self._patch_probes({}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        assert data["healthy"] is True

    def test_healthy_false_when_one_down(self, client, tmp_path):
        with self._patch_probes({"ping_redis": {"ok": False, "detail": "timeout"}}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        assert data["healthy"] is False
        assert data["connections"]["redis"]["ok"] is False

    def test_redis_sources_reflect_live_surfaces(self, client, tmp_path):
        with self._patch_probes({
            "ping_redis": {"ok": True, "latency_ms": 1.0},
            "probe_redisvl": {"ok": False, "detail": "no query engine"},
        }):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        # Redis up, RedisVL down -> only the digest store is a live surface.
        assert data["redis_sources"] == ["Digest store"]

    def test_metrics_count_frozen_digest_papers(self, client, tmp_path):
        entries = [_digest_entry(str(i)) for i in range(3)]
        (tmp_path / "2026-06-19.json").write_text(
            json.dumps(entries), encoding="utf-8")
        with self._patch_probes({}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                data = client.get("/status").json()
        assert data["metrics"]["papers_processed_total"] == 3
        assert data["metrics"]["last_processed_at"]  # populated from file mtime

    def test_metrics_memory_records_from_profile(self, client, tmp_path):
        with self._patch_probes({}):
            with patch("app.main._DIGEST_DIR", tmp_path):
                with patch("app.memory.load_profile", return_value=_make_profile()):
                    data = client.get("/status").json()
        assert data["metrics"]["memory_records"] == 1  # _make_profile has 1 item


# ---------------------------------------------------------------------------
# POST /pipeline/search  (dev-ui pipeline panel)
# ---------------------------------------------------------------------------

class TestPipelineSearchRoute:
    def _fake_result(self):
        result = MagicMock()
        paper = MagicMock()
        paper.to_dict.return_value = {
            "source": "pubmed", "source_id": "1", "title": "P1",
            "abstract": "a", "authors": [], "doi": None, "url": None,
            "journal": None, "published": "2026-06-19", "categories": [],
            "uid": "pubmed:1", "raw": {"drop": "me"},
        }
        result.papers = [paper]
        result.counts = {"pubmed": 2, "arxiv": 1}
        result.errors = {}
        return result

    def test_returns_papers_and_counts(self, client):
        fake_pipeline = MagicMock()
        fake_pipeline.fetch.return_value = self._fake_result()
        with patch("system_pieces.data_pipeline.DataPipeline",
                   return_value=fake_pipeline):
            data = client.post("/pipeline/search",
                               json={"query": "gut microbiome"}).json()
        assert len(data["papers"]) == 1
        assert data["counts"] == {"pubmed": 2, "arxiv": 1}
        # The bulky raw payload is stripped before returning.
        assert "raw" not in data["papers"][0]

    def test_nature_source_is_filtered_out(self, client):
        captured = {}
        fake_pipeline = MagicMock()
        fake_pipeline.fetch.return_value = self._fake_result()

        def capture_init(sources=None):
            captured["sources"] = sources
            return fake_pipeline

        with patch("system_pieces.data_pipeline.DataPipeline",
                   side_effect=capture_init):
            client.post("/pipeline/search",
                        json={"query": "q", "sources": ["pubmed", "nature"]})
        assert "nature" not in captured["sources"]

    def test_pipeline_error_returns_error_payload(self, client):
        with patch("system_pieces.data_pipeline.DataPipeline",
                   side_effect=RuntimeError("boom")):
            data = client.post("/pipeline/search", json={"query": "q"}).json()
        assert data["papers"] == []
        assert "pipeline" in data["errors"]

    def test_search_populates_pipeline_metrics_cache(self, client, tmp_path):
        fake_pipeline = MagicMock()
        fake_pipeline.fetch.return_value = self._fake_result()
        with patch("system_pieces.data_pipeline.DataPipeline",
                   return_value=fake_pipeline):
            client.post("/pipeline/search", json={"query": "fiber"})
        # The cached pipeline metrics surface on the next /status call.
        with patch("app.main._DIGEST_DIR", tmp_path):
            import app.main as main
            with patch.object(main, "_probe",
                              side_effect=lambda fn: {"ok": True, "latency_ms": 1.0}):
                status = client.get("/status").json()
        assert status["metrics"]["pipeline_last_query"] == "fiber"
        assert status["metrics"]["pipeline_source_counts"] == {"pubmed": 2, "arxiv": 1}
