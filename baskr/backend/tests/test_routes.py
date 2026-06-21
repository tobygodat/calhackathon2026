"""Integration tests for the FastAPI routes (app/main.py).

Routes use lazy imports. We patch at the SOURCE modules:
  - app.memory.load_profile     (get_profile, add_memory routes)
  - app.memory.append_item      (add_memory route)
  - app.main._probe             (/status probes — patched to avoid network)
"""

from __future__ import annotations

import io
import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Profile,
    ProfileItem,
    ProfileItemKind,
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
# No search / digest / pipeline routes remain
# ---------------------------------------------------------------------------

class TestRemovedRoutes:
    # The team route surface (test_api.py) restores /api/search and /api/digest/*,
    # so only the dev-only /pipeline/search alias and a missing dated digest 404.
    @pytest.mark.parametrize("method,path", [
        ("post", "/pipeline/search"),
        ("get", "/api/digest/2024-03-15"),
    ])
    def test_route_is_gone(self, client, method, path):
        if method == "post":
            resp = client.post(path, json={})
        else:
            resp = client.get(path)
        assert resp.status_code == 404


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

        def capture(kind, text, settings=None):
            captured.update({"kind": kind, "text": text})
            return _make_profile()

        with patch("app.memory.append_item", side_effect=capture):
            client.post("/api/profile/memory",
                        json={"kind": "assumption", "text": "We assume X."})
        assert captured["kind"] == ProfileItemKind.ASSUMPTION
        assert captured["text"] == "We assume X."


# ---------------------------------------------------------------------------
# GET /ledger
# ---------------------------------------------------------------------------

class TestLedgerRoute:
    def test_empty_when_no_papers(self, client):
        # Autouse conftest fixture repoints the CSV at an empty tmp dir.
        assert client.get("/api/ledger").json() == []

    def test_returns_recorded_papers_newest_first(self, client):
        import app.monitoring as mon
        mon.record_papers([{"source": "pubmed", "source_id": "1", "title": "Older"}])
        mon.record_papers([{"source": "arxiv", "source_id": "2", "title": "Newer"}])
        data = client.get("/api/ledger").json()
        assert [r["title"] for r in data] == ["Newer", "Older"]
        for r in data:
            assert set(r) == {"title", "first_seen_at", "source"}
            assert r["first_seen_at"].endswith("Z")


# ---------------------------------------------------------------------------
# POST /intake
# ---------------------------------------------------------------------------

def _upload(name: str, payload) -> tuple[str, tuple]:
    blob = json.dumps(payload).encode("utf-8")
    return ("files", (name, io.BytesIO(blob), "application/json"))


class TestIntakeRoute:
    def test_single_paper_object(self, client):
        paper = {"source": "pubmed", "source_id": "1", "title": "A paper"}
        resp = client.post("/api/intake", files=[_upload("p.json", paper)])
        assert resp.status_code == 200
        body = resp.json()
        # Redis is unavailable in the sandbox, so streamed may be 0 — but the
        # paper must still be recorded to the ledger.
        assert body["recorded"] == 1
        assert body["skipped"] == 0
        assert set(body) == {"streamed", "recorded", "skipped", "errors", "ids"}
        # Ledger reflects the recorded paper.
        assert client.get("/api/ledger").json()[0]["title"] == "A paper"

    def test_array_of_papers(self, client):
        papers = [
            {"source": "pubmed", "source_id": "1", "title": "One"},
            {"source": "arxiv", "source_id": "2", "title": "Two"},
        ]
        resp = client.post("/api/intake", files=[_upload("batch.json", papers)])
        body = resp.json()
        assert body["recorded"] == 2

    def test_missing_title_is_skipped(self, client):
        papers = [
            {"source": "pubmed", "source_id": "1", "title": "Has title"},
            {"source": "pubmed", "source_id": "2"},  # no title
        ]
        resp = client.post("/api/intake", files=[_upload("mix.json", papers)])
        body = resp.json()
        assert body["recorded"] == 1
        assert body["skipped"] == 1

    def test_bad_json_file_records_error(self, client):
        bad = ("files", ("broken.json", io.BytesIO(b"{not json"),
                          "application/json"))
        resp = client.post("/api/intake", files=[bad])
        assert resp.status_code == 200
        body = resp.json()
        assert "broken.json" in body["errors"]
        assert body["recorded"] == 0

    def test_streams_when_redis_available(self, client):
        # Force the stream XADD to succeed regardless of a live Redis.
        with patch("app.streams.add_new_paper", return_value="1-0"):
            resp = client.post(
                "/api/intake",
                files=[_upload("p.json",
                               {"source": "pubmed", "source_id": "9", "title": "Streamed"})],
            )
        body = resp.json()
        assert body["streamed"] == 1
        assert body["ids"] == ["1-0"]

    def test_redis_outage_does_not_500(self, client):
        with patch("app.streams.add_new_paper", side_effect=RuntimeError("redis down")):
            resp = client.post(
                "/api/intake",
                files=[_upload("p.json",
                               {"source": "pubmed", "source_id": "5", "title": "T"})],
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["recorded"] == 1
        assert body["streamed"] == 0
        assert any("redis down" in v for v in body["errors"].values())

    def test_multiple_files(self, client):
        f1 = _upload("a.json", {"source": "pubmed", "source_id": "1", "title": "A"})
        f2 = _upload("b.json", [{"source": "arxiv", "source_id": "2", "title": "B"}])
        resp = client.post("/api/intake", files=[f1, f2])
        body = resp.json()
        assert body["recorded"] == 2

    def test_stream_fields_match_producer_schema(self, client):
        captured = {}

        def capture(fields, *a, **k):
            captured.update(fields)
            return "1-0"

        with patch("app.streams.add_new_paper", side_effect=capture):
            client.post(
                "/api/intake",
                files=[_upload("p.json", {
                    "source": "pubmed", "source_id": "1", "title": "T",
                    "authors": ["X", "Y"], "abstract": "abs",
                })],
            )
        assert set(captured) == {
            "uid", "source", "source_id", "title", "abstract",
            "authors", "doi", "url", "journal", "published",
        }
        # authors are JSON-encoded; missing fields default to "".
        assert json.loads(captured["authors"]) == ["X", "Y"]
        assert captured["doi"] == ""
        assert captured["uid"] == "pubmed:1"


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

    def test_returns_expected_shape(self, client):
        with self._patch_probes({}):
            data = client.get("/api/status").json()
        assert {"healthy", "connections", "metrics", "redis_sources"}.issubset(data)
        # The restored dashboard contract probes the data sources plus the
        # feature-level Redis surfaces and external APIs (see test_smoke.py).
        assert {
            "pubmed", "arxiv", "biorxiv", "redis", "redisvl",
            "streams", "agent_memory", "langcache", "openai",
            "anthropic", "consumer",
        }.issubset(data["connections"])

    def test_new_data_sources_probed(self, client):
        # OpenAlex, ChemRxiv and medRxiv must appear in the connections map so
        # the dev-UI can surface them. Offline these probes may report ok=False;
        # we assert presence and shape, not that they are up.
        with self._patch_probes({}):
            connections = client.get("/api/status").json()["connections"]
        for key in ("openalex", "chemrxiv", "medrxiv"):
            assert key in connections, f"missing data source: {key}"
            assert isinstance(connections[key], dict)
            assert isinstance(connections[key]["ok"], bool)

    def test_metrics_include_new_papers_seen(self, client):
        with self._patch_probes({}):
            data = client.get("/api/status").json()
        assert "new_papers_seen" in data["metrics"]
        assert isinstance(data["metrics"]["new_papers_seen"], int)

    def test_metrics_time_based_keys_present(self, client):
        with self._patch_probes({}):
            metrics = client.get("/api/status").json()["metrics"]
        for key in (
            "last_new_paper_at", "seconds_since_last_new_paper",
            "new_papers_last_hour", "status_flip_counts", "status_flip_series",
            "last_processed_at",
        ):
            assert key in metrics

    def test_no_pipeline_metrics(self, client):
        # papers_processed_* are part of the restored dashboard contract
        # (test_smoke.py); only the per-request pipeline_* keys stay absent.
        with self._patch_probes({}):
            metrics = client.get("/api/status").json()["metrics"]
        for key in ("pipeline_last_query", "pipeline_source_counts"):
            assert key not in metrics

    def test_seconds_since_last_new_paper_tracks_ledger(self, client):
        import app.monitoring as mon
        mon.record_papers([{"source": "pubmed", "source_id": "1", "title": "T"}])
        with self._patch_probes({}):
            metrics = client.get("/api/status").json()["metrics"]
        assert metrics["last_new_paper_at"] is not None
        assert isinstance(metrics["seconds_since_last_new_paper"], int)
        assert metrics["last_processed_at"] == metrics["last_new_paper_at"]

    def test_status_flip_series_shape(self, client):
        import app.monitoring as mon
        mon.record_status({"redis": {"ok": True}})   # baseline
        mon.record_status({"redis": {"ok": False}})  # flip off
        with self._patch_probes({"ping_redis": {"ok": False, "detail": "x"}}):
            series = client.get("/api/status").json()["metrics"]["status_flip_series"]
        assert isinstance(series, list)
        assert all(set(e) == {"connection", "changed_at", "transition"} for e in series)

    def test_healthy_true_when_all_ok(self, client):
        with self._patch_probes({}):
            data = client.get("/api/status").json()
        assert data["healthy"] is True

    def test_healthy_false_when_one_down(self, client):
        with self._patch_probes({"ping_redis": {"ok": False, "detail": "timeout"}}):
            data = client.get("/api/status").json()
        assert data["healthy"] is False
        assert data["connections"]["redis"]["ok"] is False

    def test_redis_sources_reflect_live_surfaces(self, client):
        with self._patch_probes({
            "ping_redis": {"ok": True, "latency_ms": 1.0},
            "probe_redisvl": {"ok": False, "detail": "no query engine"},
        }):
            data = client.get("/api/status").json()
        # Redis up, RedisVL down -> only the digest store is a live surface.
        assert data["redis_sources"] == ["Digest store"]

    def test_metrics_memory_records_from_profile(self, client):
        with self._patch_probes({}):
            with patch("app.memory.load_profile", return_value=_make_profile()):
                data = client.get("/api/status").json()
        assert data["metrics"]["memory_records"] == 1  # _make_profile has 1 item


# ---------------------------------------------------------------------------
# _pubmed_probe / cache behaviour
# ---------------------------------------------------------------------------

class TestPubmedProbeCache:
    """Unit tests for the module-level PubMed probe cache in app/main.py.

    These bypass _probe() and call _pubmed_probe() directly so we can assert
    on cache state and request counts without starting the full /status route.
    """

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        import app.main as main
        main._reset_pubmed_cache()
        yield
        main._reset_pubmed_cache()

    def test_reset_clears_result_and_expiry(self):
        import app.main as main
        main._pubmed_cache_result = {}
        main._pubmed_cache_expires = float("inf")
        main._reset_pubmed_cache()
        assert main._pubmed_cache_result is None
        assert main._pubmed_cache_expires == 0.0

    def test_successful_probe_populates_cache(self):
        import app.main as main
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.raise_for_status = lambda: None
        with patch("requests.get", return_value=fake):
            main._pubmed_probe()
        assert main._pubmed_cache_result is not None
        assert main._pubmed_cache_expires > time.monotonic()

    def test_cache_hit_skips_network_call(self):
        import app.main as main
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.raise_for_status = lambda: None
        with patch("requests.get", return_value=fake) as mock_get:
            main._pubmed_probe()  # cold — hits network
            main._pubmed_probe()  # warm — should use cache
        assert mock_get.call_count == 1

    def test_expired_cache_triggers_new_network_call(self):
        import app.main as main
        from unittest.mock import MagicMock
        # Seed an expired cache entry.
        main._pubmed_cache_result = {}
        main._pubmed_cache_expires = time.monotonic() - 1.0
        fake = MagicMock()
        fake.raise_for_status = lambda: None
        with patch("requests.get", return_value=fake) as mock_get:
            main._pubmed_probe()
        assert mock_get.call_count == 1

    def test_failed_probe_does_not_update_cache(self):
        import app.main as main
        with patch("requests.get", side_effect=ConnectionError("ncbi down")):
            with pytest.raises(ConnectionError):
                main._pubmed_probe()
        assert main._pubmed_cache_result is None

    def test_failed_probe_does_not_evict_valid_cache(self):
        import app.main as main
        from unittest.mock import MagicMock
        # Warm the cache first.
        fake = MagicMock()
        fake.raise_for_status = lambda: None
        with patch("requests.get", return_value=fake):
            main._pubmed_probe()
        cached_expiry = main._pubmed_cache_expires
        # Now expire the cache and make the next call fail.
        main._pubmed_cache_expires = time.monotonic() - 1.0
        with patch("requests.get", side_effect=ConnectionError("timeout")):
            with pytest.raises(ConnectionError):
                main._pubmed_probe()
        # Cache was NOT overwritten with None after a failed refresh.
        assert main._pubmed_cache_result is not None

    def test_probe_timeout_is_8_seconds(self):
        """_pubmed_probe must use timeout=8, not the old timeout=5."""
        import app.main as main
        from unittest.mock import MagicMock, call
        fake = MagicMock()
        fake.raise_for_status = lambda: None
        with patch("requests.get", return_value=fake) as mock_get:
            main._pubmed_probe()
        _, kwargs = mock_get.call_args
        assert kwargs.get("timeout") == 8
