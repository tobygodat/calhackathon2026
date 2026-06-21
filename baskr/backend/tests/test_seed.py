"""Phase 3 tests for seed_profile (SPEC §5.1, §3).

``load_seed`` is a pure parse (no Redis). ``seed`` requires a LIVE Redis and is
skipped otherwise; it runs against a dedicated, flushable test DB.
"""

from __future__ import annotations

import json
import os

import pytest
import redis as _redis

from app import memory, redis_client, seed_profile
from app.config import Settings
from app.seed_profile import SEED_PATH

# Dedicated throwaway redis-stack on :6399 (RediSearch indexes only on DB 0).
_TEST_REDIS_URL = os.environ.get("BASKR_TEST_REDIS_URL", "redis://localhost:6399/0")


def _live_redis() -> bool:
    try:
        client = _redis.Redis.from_url(_TEST_REDIS_URL, socket_connect_timeout=0.5)
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def _seed_item_count() -> int:
    return len(json.loads(SEED_PATH.read_text())["items"])


# --- pure parse (no redis) --------------------------------------------------

def test_load_seed_parses_profile() -> None:
    profile = seed_profile.load_seed()
    assert profile.lab_id == "gut-microbiome-demo"
    assert profile.niche == "gut_microbiome"
    assert len(profile.items) == _seed_item_count()
    assert {it.kind.value for it in profile.items} <= {
        "open_question", "assumption", "finding", "planned_experiment",
    }


# --- live seed round-trip ---------------------------------------------------

@pytest.mark.skipif(not _live_redis(), reason="live redis not reachable")
class TestSeedLive:
    @pytest.fixture()
    def settings(self) -> Settings:
        return Settings(redis_url=_TEST_REDIS_URL, lab_id="seed-test-lab")

    @pytest.fixture(autouse=True)
    def clean_db(self, settings):
        client = _redis.Redis.from_url(_TEST_REDIS_URL)
        client.flushdb()
        redis_client._INDEXES.clear()
        redis_client._CLIENTS.clear()
        yield
        client.flushdb()
        redis_client._INDEXES.clear()
        redis_client._CLIENTS.clear()

    def test_seed_writes_items(self, settings) -> None:
        expected = _seed_item_count()
        count = seed_profile.seed(settings)
        assert count == expected
        assert memory.profile_item_count(settings) == expected

        profile = memory.load_profile(settings)
        assert profile.lab_id == "gut-microbiome-demo"
        assert len(profile.items) == expected

    def test_seed_is_idempotent(self, settings) -> None:
        expected = _seed_item_count()
        seed_profile.seed(settings)
        seed_profile.seed(settings)  # re-run must not duplicate
        assert memory.profile_item_count(settings) == expected
