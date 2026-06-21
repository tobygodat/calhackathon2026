"""Phase 3 INTEGRATION tests for ingest (live Redis).

Network to PubMed/arXiv/bioRxiv is egress-blocked in this sandbox, so ``fetch_recent``
exercises its STAGED fallback; either way it must return >=1 PaperOut and ``ingest``
must index them (corpus_index_docs increases). Runs against a dedicated test DB +
test-only key prefixes and cleans up.
"""

from __future__ import annotations

import os

import pytest
import redis as _redis

from app import ingest, redis_client, status as status_probe
from app.config import Settings
from app.models import PaperOut

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
        lab_id="ingest-test-lab",
        papers_index="baskr:idx:papers_ingest_test",
        paper_key_prefix="baskr:paper_ingest_test:",
        digest_key_prefix="baskr:digest_ingest_test:",
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


def test_fetch_recent_returns_papers(settings) -> None:
    papers = ingest.fetch_recent("gut microbiome fiber", days=7, settings=settings)
    assert len(papers) >= 1
    assert all(isinstance(p, PaperOut) for p in papers)
    assert all(p.title for p in papers)


def test_ingest_indexes_papers_and_increases_corpus(settings) -> None:
    before = status_probe.build_metrics(settings)["corpus_index_docs"]

    count = ingest.ingest("gut microbiome fiber", days=7, settings=settings)
    assert count >= 1

    after = status_probe.build_metrics(settings)["corpus_index_docs"]
    assert after >= before + count
