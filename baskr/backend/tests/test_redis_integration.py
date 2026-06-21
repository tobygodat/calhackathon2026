"""Phase 1 INTEGRATION tests — require a LIVE local Redis.

Skipped automatically if ``PING`` fails. To avoid polluting real data, every test
runs against a dedicated test DB (``redis://localhost:6379/15``) which is FLUSHED
in setup/teardown, and uses test-only key prefixes.
"""

from __future__ import annotations

import hashlib
import os
import struct

import pytest
import redis as _redis

from app import langcache, memory, redis_client, streams, status as status_probe
from app.config import Settings
from app.models import ProfileItemKind

# Dedicated, flushable test DB so we never touch db 0.
# RediSearch (FT.CREATE) only works on DB 0, so a dedicated throwaway redis-stack
# instance on port 6399 is used for index-backed integration tests (flushdb-safe,
# never touches the dev data on :6379). Override with BASKR_TEST_REDIS_URL.
_TEST_REDIS_URL = os.environ.get("BASKR_TEST_REDIS_URL", "redis://localhost:6399/0")
_EMBED_DIM = Settings().embed_dim


def _live_redis() -> bool:
    try:
        client = _redis.Redis.from_url(_TEST_REDIS_URL, socket_connect_timeout=0.5)
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _live_redis(), reason="live redis not reachable")


def _fake_embedding(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Deterministic placeholder vector (DEV/TEST helper — no OpenAI call).

    Hashes the text into a reproducible pseudo-random float32 vector. Identical text
    -> identical vector, so a paper is its own nearest neighbour.
    """
    seed = hashlib.sha256(text.encode()).digest()
    out: list[float] = []
    counter = 0
    while len(out) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(block), 4):
            if len(out) >= dim:
                break
            (val,) = struct.unpack("<I", block[i:i + 4])
            out.append((val / 0xFFFFFFFF) * 2.0 - 1.0)  # -> [-1, 1)
        counter += 1
    return out


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        redis_url=_TEST_REDIS_URL,
        lab_id="integration-test-lab",
        papers_index="baskr:idx:papers_test",
        paper_key_prefix="baskr:paper_test:",
        digest_key_prefix="baskr:digest_test:",
    )


@pytest.fixture(autouse=True)
def clean_db(settings):
    """Flush the test DB before and after, and reset cached redisvl handles."""
    client = _redis.Redis.from_url(_TEST_REDIS_URL)
    client.flushdb()
    redis_client._INDEXES.clear()
    redis_client._CLIENTS.clear()
    yield
    client.flushdb()
    redis_client._INDEXES.clear()
    redis_client._CLIENTS.clear()


# --- index idempotency ------------------------------------------------------

def test_ensure_papers_index_idempotent(settings) -> None:
    idx1 = redis_client.ensure_papers_index(settings)
    assert idx1.exists()
    # Creating again must not raise.
    redis_client._INDEXES.clear()
    idx2 = redis_client.ensure_papers_index(settings)
    assert idx2.exists()
    assert idx1.name == idx2.name


# --- upsert + nearest-neighbour --------------------------------------------

def test_upsert_and_query_similar_self_is_nearest(settings) -> None:
    redis_client.ensure_papers_index(settings)
    target_text = "butyrate producing bacteria expand regulatory T cells in the gut"
    target_uid = "pubmed:TARGET"
    redis_client.upsert_paper(
        target_uid,
        {"source": "pubmed", "source_id": "TARGET", "title": "Butyrate & Tregs",
         "abstract": target_text, "authors": ["A. One", "B. Two"],
         "categories": ["immunology"]},
        _fake_embedding(target_text),
        settings,
    )
    # A few distractor papers with different vectors.
    for n in range(3):
        text = f"unrelated paper about astrophysics number {n}"
        redis_client.upsert_paper(
            f"arxiv:{n}",
            {"source": "arxiv", "source_id": str(n), "title": f"Distractor {n}",
             "abstract": text},
            _fake_embedding(text),
            settings,
        )

    results = redis_client.query_similar(_fake_embedding(target_text), k=3, settings=settings)
    assert results, "expected at least one result"
    assert results[0]["uid"] == target_uid
    # Metadata round-trips, including list fields.
    assert results[0]["title"] == "Butyrate & Tregs"
    assert results[0]["authors"] == ["A. One", "B. Two"]


# --- digest round-trip ------------------------------------------------------

def test_store_and_load_digest(settings) -> None:
    payload = '{"date": "2026-06-21", "entries": [{"x": 1}]}'
    redis_client.store_digest("2026-06-21", payload, settings)
    assert redis_client.load_digest("2026-06-21", settings) == payload
    assert redis_client.load_digest("2000-01-01", settings) is None


# --- memory live round-trip -------------------------------------------------

def test_memory_live_round_trip(settings) -> None:
    memory.append_item(ProfileItemKind.FINDING, "live finding about butyrate", settings)
    memory.append_item(ProfileItemKind.OPEN_QUESTION, "live open question about fiber", settings)
    profile = memory.load_profile(settings)
    assert len(profile.items) == 2
    top = memory.retrieve_relevant("butyrate", k=1, settings=settings)
    assert "butyrate" in top[0].text


# --- /status integration ----------------------------------------------------

def test_status_reflects_live_upserts(settings) -> None:
    """get_status(settings) reflects real Redis reads after upserts."""
    text = "indexed paper for status check"
    redis_client.upsert_paper(
        "pubmed:STATUS",
        {"source": "pubmed", "source_id": "STATUS", "title": "Status Paper", "abstract": text},
        _fake_embedding(text),
        settings,
    )
    memory.append_item(ProfileItemKind.FINDING, "status finding", settings)
    streams.add_new_paper({"uid": "pubmed:STATUS"}, settings)

    body = status_probe.get_status(settings)

    assert body["connections"]["redis"]["ok"] is True
    assert body["connections"]["redisvl"]["ok"] is True
    assert "docs" in body["connections"]["redisvl"]["detail"]
    assert body["metrics"]["corpus_index_docs"] >= 1
    assert body["metrics"]["memory_records"] >= 1
    assert body["metrics"]["stream_length"] >= 1
