"""Phase 1 UNIT tests — run against fakeredis, NO live redis required.

``get_client`` is monkeypatched to a single shared ``fakeredis`` instance so the
memory + digest round-trips exercise the real code paths without a server.
"""

from __future__ import annotations

import fakeredis
import pytest

from app import langcache, memory, redis_client, streams
from app.config import Settings
from app.models import ProfileItemKind


@pytest.fixture()
def settings() -> Settings:
    return Settings(redis_url="redis://fake", lab_id="unit-test-lab")


@pytest.fixture(autouse=True)
def fake_client(monkeypatch) -> fakeredis.FakeRedis:
    """Patch every module's ``get_client`` to one shared fakeredis instance."""
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(redis_client, "get_client", lambda settings=None: fake)
    monkeypatch.setattr(memory, "get_client", lambda settings=None: fake)
    monkeypatch.setattr(streams, "get_client", lambda settings=None: fake)
    monkeypatch.setattr(langcache, "get_client", lambda settings=None: fake)
    return fake


# --- memory round-trip ------------------------------------------------------

def test_memory_append_and_load_round_trip(settings) -> None:
    profile = memory.append_item(ProfileItemKind.FINDING, "SCFA butyrate boosts Treg cells", settings)
    assert profile.lab_id == settings.lab_id
    assert len(profile.items) == 1
    item = profile.items[0]
    assert item.kind is ProfileItemKind.FINDING
    assert item.id.startswith("fnd_")

    reloaded = memory.load_profile(settings)
    assert {i.text for i in reloaded.items} == {"SCFA butyrate boosts Treg cells"}


def test_memory_append_assigns_unique_ids(settings) -> None:
    memory.append_item(ProfileItemKind.OPEN_QUESTION, "Does fiber alter microbiome diversity?", settings)
    memory.append_item(ProfileItemKind.OPEN_QUESTION, "Is there a gut-brain axis link?", settings)
    ids = [i.id for i in memory.load_profile(settings).items]
    assert ids == sorted(set(ids))
    assert len(ids) == 2


def test_memory_retrieve_relevant_ranks_by_overlap(settings, monkeypatch) -> None:
    # This test exercises the LEXICAL fallback ranker specifically. Phase 2 made the
    # semantic embedding path the default; the deterministic hashed embedder carries
    # no lexical semantics, so force the lexical fallback here.
    monkeypatch.setattr(memory, "_semantic_rank", lambda *a, **k: None)

    memory.append_item(ProfileItemKind.FINDING, "butyrate increases regulatory T cells in the gut", settings)
    memory.append_item(ProfileItemKind.ASSUMPTION, "diet composition is stable across subjects", settings)
    memory.append_item(ProfileItemKind.OPEN_QUESTION, "how does fiber intake affect butyrate production", settings)

    top = memory.retrieve_relevant("butyrate regulatory T cells gut", k=2, settings=settings)
    assert len(top) == 2
    # The finding about butyrate + Treg cells should rank first.
    assert "regulatory T cells" in top[0].text


def test_memory_retrieve_respects_k(settings) -> None:
    for n in range(5):
        memory.append_item(ProfileItemKind.FINDING, f"finding number {n} about microbiome", settings)
    assert len(memory.retrieve_relevant("microbiome", k=3, settings=settings)) == 3


def test_profile_item_count(settings) -> None:
    assert memory.profile_item_count(settings) == 0
    memory.append_item(ProfileItemKind.FINDING, "x", settings)
    assert memory.profile_item_count(settings) == 1


# --- digest round-trip ------------------------------------------------------

def test_digest_store_and_load(settings) -> None:
    payload = '{"date": "2026-06-21", "entries": []}'
    redis_client.store_digest("2026-06-21", payload, settings)
    assert redis_client.load_digest("2026-06-21", settings) == payload


def test_digest_load_missing_returns_none(settings) -> None:
    assert redis_client.load_digest("1999-01-01", settings) is None


# --- streams + langcache stubs ---------------------------------------------

def test_streams_add_and_length(settings) -> None:
    assert streams.stream_length(settings) == 0
    streams.add_new_paper({"uid": "pubmed:1", "title": "t"}, settings)
    streams.add_new_paper({"uid": "pubmed:2", "title": "t2"}, settings)
    assert streams.stream_length(settings) == 2


def test_langcache_get_set_and_stats(settings) -> None:
    assert langcache.get("query a", settings) is None  # miss
    langcache.set("query a", "result-a", settings=settings)
    assert langcache.get("query a", settings) == "result-a"  # hit
    s = langcache.stats(settings)
    assert s["hits"] == 1 and s["misses"] == 1
    assert s["hit_rate"] == 0.5
