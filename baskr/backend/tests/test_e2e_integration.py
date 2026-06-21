"""Phase 3 END-TO-END integration (live Redis) — the headline gate.

Seeds the profile, ingests staged papers, then runs the full engine on a known
paper: embed -> retrieve (semantic, live memory) -> build_prompt -> classify.
Asserts a schema-valid Classification with a valid Label comes out the other end.
Runs against a dedicated test DB and cleans up.
"""

from __future__ import annotations

import os

import pytest
import redis as _redis

from app import engine, ingest, memory, redis_client, seed_profile
from app.config import Settings
from app.models import Classification, Label

# Dedicated throwaway redis-stack on :6399 (RediSearch indexes only on DB 0).
_TEST_REDIS_URL = os.environ.get("BASKR_TEST_REDIS_URL", "redis://localhost:6399/0")


def _live_redis() -> bool:
    try:
        client = _redis.Redis.from_url(_TEST_REDIS_URL, socket_connect_timeout=0.5)
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _live_redis(), reason="live redis not reachable")


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        redis_url=_TEST_REDIS_URL,
        lab_id="e2e-test-lab",
        papers_index="baskr:idx:papers_e2e_test",
        paper_key_prefix="baskr:paper_e2e_test:",
        digest_key_prefix="baskr:digest_e2e_test:",
    )


@pytest.fixture(autouse=True)
def clean_db(settings):
    client = _redis.Redis.from_url(_TEST_REDIS_URL)
    client.flushdb()
    redis_client._INDEXES.clear()
    redis_client._CLIENTS.clear()
    yield
    client.flushdb()
    redis_client._INDEXES.clear()
    redis_client._CLIENTS.clear()


def test_end_to_end_seed_ingest_classify(settings) -> None:
    # 1. seed the lab profile into live Agent Memory.
    seeded = seed_profile.seed(settings)
    assert seeded >= 1
    assert memory.profile_item_count(settings) >= 1

    # 2. ingest staged papers into the live RedisVL index.
    count = ingest.ingest("dietary fiber gut microbiome diversity", days=7, settings=settings)
    assert count >= 1

    # 3. take a known staged paper and run the full engine against the live profile.
    papers = ingest.fetch_recent("dietary fiber gut microbiome diversity", days=7,
                                 settings=settings)
    target = papers[0]
    profile = memory.load_profile(settings)

    classification = engine.classify_paper(target, profile, settings)

    # 4. assert a schema-valid Classification with a valid Label end to end.
    assert isinstance(classification, Classification)
    assert isinstance(classification.label, Label)
    assert classification.label in set(Label)
    assert 0.0 <= classification.confidence <= 1.0
    assert isinstance(classification.reason, str) and classification.reason
