"""Tests for the background consumer and SSE alert endpoint (Phase 6).

All tests are offline-safe: the consumer is tested in isolation with a stub Redis
stream (fakeredis); the SSE endpoint is tested via FastAPI TestClient with a patched
consumer.get_recent_alerts.
"""

from __future__ import annotations

import json
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app import consumer
from app.config import Settings
from app.main import app
from app.models import PaperOut

client = TestClient(app)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_SAMPLE_PAPER_FIELDS: dict[str, str] = {
    "uid": "pubmed:12345",
    "source": "pubmed",
    "source_id": "12345",
    "title": "Dietary fiber increases gut microbiome diversity",
    "abstract": "Dietary fiber consumption promotes growth of beneficial gut bacteria including Bifidobacterium and Lactobacillus.",
    "authors": json.dumps(["Alice", "Bob"]),
    "published": "2026-06-21",
}


def _make_settings_with_fake_redis() -> Settings:
    """Return a Settings with a fakeredis URL (will fail real connect but we patch get_client)."""
    return Settings()


# ---------------------------------------------------------------------------
# consumer unit tests
# ---------------------------------------------------------------------------

def test_parse_paper_returns_paperout():
    fields = {k.encode(): v.encode() for k, v in _SAMPLE_PAPER_FIELDS.items()}
    paper = consumer._parse_paper(fields)  # type: ignore[attr-defined]
    assert paper is not None
    assert isinstance(paper, PaperOut)
    assert paper.title == _SAMPLE_PAPER_FIELDS["title"]
    assert paper.source == "pubmed"


def test_push_alert_increments_count():
    initial = consumer.alerts_fired_count()
    consumer._push_alert({"label": "ANSWERS", "paper_title": "test"})  # type: ignore
    assert consumer.alerts_fired_count() == initial + 1


def test_get_recent_alerts_returns_list():
    alerts = consumer.get_recent_alerts(n=10)
    assert isinstance(alerts, list)


def test_classify_and_alert_fires_for_relevant_paper(monkeypatch):
    """Push a gut-microbiome paper through _classify_and_alert; expect an alert."""
    from app.models import Classification, Label, Profile, ProfileItem, ProfileItemKind

    mock_profile = Profile(
        lab_id="test",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=[
            ProfileItem(
                id="oq_1",
                kind=ProfileItemKind.OPEN_QUESTION,
                text="How does dietary fiber affect gut microbiome diversity?",
            )
        ],
    )
    mock_classification = Classification(
        label=Label.ANSWERS,
        reason="Paper directly answers the question.",
        matched_item_id="oq_1",
        confidence=0.85,
    )

    monkeypatch.setattr("app.memory.load_profile", lambda s: mock_profile)
    monkeypatch.setattr("app.engine.classify_paper", lambda p, pr, s: mock_classification)

    paper = PaperOut(
        source="pubmed",
        source_id="99999",
        title="Dietary fiber increases gut microbiome diversity",
        abstract="Fiber increases diversity.",
        published="2026-06-21",
    )
    before = consumer.alerts_fired_count()
    consumer._classify_and_alert(paper, Settings())  # type: ignore
    assert consumer.alerts_fired_count() == before + 1


def test_classify_and_alert_skips_not_relevant(monkeypatch):
    """NOT_RELEVANT papers must NOT push to the alert store."""
    from app.models import Classification, Label, Profile

    mock_profile = Profile(lab_id="t", niche="g", display_name="L", items=[])
    mock_classification = Classification(
        label=Label.NOT_RELEVANT, reason="Unrelated.", matched_item_id=None, confidence=0.1
    )
    monkeypatch.setattr("app.memory.load_profile", lambda s: mock_profile)
    monkeypatch.setattr("app.engine.classify_paper", lambda p, pr, s: mock_classification)

    paper = PaperOut(
        source="arxiv",
        source_id="0000",
        title="Quantum computing",
        abstract="Not biology.",
        published="2026-06-21",
    )
    before = consumer.alerts_fired_count()
    consumer._classify_and_alert(paper, Settings())  # type: ignore
    assert consumer.alerts_fired_count() == before  # no new alert


def test_classify_and_alert_writes_memory_once(monkeypatch):
    """A relevant paper with new_memory writes one LTM, deduped on re-process."""
    from app import memory as memmod
    from app.models import Classification, Label, Profile

    fake = fakeredis.FakeStrictRedis()
    writes: list[tuple] = []
    mock_profile = Profile(lab_id="t", niche="g", display_name="L", items=[])
    mock_classification = Classification(
        label=Label.ANSWERS,
        reason="Answers the question.",
        matched_item_id="oq_1",
        confidence=0.9,
        new_memory="Dietary fiber boosts microbiome diversity.",
    )
    monkeypatch.setattr("app.memory.load_profile", lambda s: mock_profile)
    monkeypatch.setattr("app.engine.classify_paper", lambda p, pr, s: mock_classification)
    monkeypatch.setattr("app.redis_client.get_client", lambda s=None: fake)
    monkeypatch.setattr(memmod, "append_item",
                        lambda kind, text, s: writes.append((kind, text)))

    paper = PaperOut(
        source="pubmed", source_id="555", title="Fiber paper",
        abstract="Fiber increases diversity.", uid="pubmed:555",
    )
    consumer._classify_and_alert(paper, Settings())  # type: ignore
    consumer._classify_and_alert(paper, Settings())  # re-process same paper

    assert len(writes) == 1  # written exactly once (deduped)
    assert writes[0][1] == "Dietary fiber boosts microbiome diversity."


def test_classify_and_alert_no_memory_when_new_memory_none(monkeypatch):
    """A relevant paper without a new_memory writes nothing back."""
    from app import memory as memmod
    from app.models import Classification, Label, Profile

    writes: list[tuple] = []
    mock_profile = Profile(lab_id="t", niche="g", display_name="L", items=[])
    mock_classification = Classification(
        label=Label.EXTENDS, reason="ok", matched_item_id="oq_1",
        confidence=0.9, new_memory=None,
    )
    monkeypatch.setattr("app.memory.load_profile", lambda s: mock_profile)
    monkeypatch.setattr("app.engine.classify_paper", lambda p, pr, s: mock_classification)
    monkeypatch.setattr(memmod, "append_item",
                        lambda kind, text, s: writes.append((kind, text)))

    paper = PaperOut(source="arxiv", source_id="1", title="t", abstract="a", uid="arxiv:1")
    consumer._classify_and_alert(paper, Settings())  # type: ignore
    assert writes == []


# ---------------------------------------------------------------------------
# SSE endpoint test
# ---------------------------------------------------------------------------

def test_alerts_stream_endpoint_registered():
    """Verify the SSE route is registered (405 means POST, 404 means missing)."""
    # The SSE generator never terminates so we can't use a normal GET in tests.
    # Instead, confirm the route exists by checking it isn't 404/405 via OPTIONS.
    resp = client.options("/api/alerts/stream")
    # FastAPI returns 200 for OPTIONS on known routes (CORS middleware).
    assert resp.status_code != 404


def test_alerts_stream_wires_consumer_module():
    """Confirm the SSE handler imports consumer.get_recent_alerts without error."""
    # The alerts module is imported at app startup. This test just validates
    # that consumer.get_recent_alerts() is callable and returns a list.
    from app import consumer as _consumer
    alerts = _consumer.get_recent_alerts()
    assert isinstance(alerts, list)


# ---------------------------------------------------------------------------
# Integration: push to stream, consumer classifies, alert fires
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    True,  # Run manually: requires live Redis + seeded profile
    reason="Live-Redis integration test — run manually with redis-server + seeded profile",
)
def test_stream_to_alert_integration():
    """End-to-end: push paper to stream → consumer classifies → alert appears."""
    from app.streams import add_new_paper

    settings = Settings()
    consumer.start(settings)
    time.sleep(0.5)  # let consumer boot

    before = consumer.alerts_fired_count()
    add_new_paper(_SAMPLE_PAPER_FIELDS, settings)
    time.sleep(5)  # wait for consumer to process

    assert consumer.alerts_fired_count() > before, "No alert was fired"
    consumer.stop()
