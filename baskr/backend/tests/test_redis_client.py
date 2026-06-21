"""Unit tests for the Redis client module (app/redis_client.py).

redis_client.py imports redis lazily inside get_client(), so we patch
``redis.from_url`` (the source), not ``app.redis_client.redis_lib``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

import app.redis_client as rc


@pytest.fixture(autouse=True)
def reset_redis_singletons():
    """Reset module-level singletons before/after each test."""
    rc.reset_clients()
    yield
    rc.reset_clients()


@pytest.fixture
def mock_redis_client():
    """A MagicMock that behaves like a redis.Redis client."""
    m = MagicMock()
    m.ping.return_value = True
    m.hset.return_value = 1
    m.get.return_value = None
    m.set.return_value = True
    m.keys.return_value = []
    return m


class TestGetClient:
    def test_returns_client(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            client = rc.get_client(settings)
        assert client is mock_redis_client

    def test_cached_after_first_call(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client) as mock_from_url:
            c1 = rc.get_client(settings)
            c2 = rc.get_client(settings)
        assert c1 is c2
        mock_from_url.assert_called_once()

    def test_uses_redis_url_from_settings(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client) as mock_from_url:
            rc.get_client(settings)
        mock_from_url.assert_called_once_with(
            settings.redis_url, decode_responses=True
        )


class TestStoreAndLoadDigest:
    def test_store_sets_correct_key(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.store_digest("2024-03-15", '{"entries": []}', settings)
        mock_redis_client.set.assert_called_once_with(
            f"{settings.digest_key_prefix}2024-03-15",
            '{"entries": []}',
        )

    def test_load_returns_none_when_missing(self, settings, mock_redis_client):
        mock_redis_client.get.return_value = None
        with patch("redis.from_url", return_value=mock_redis_client):
            result = rc.load_digest("2024-03-15", settings)
        assert result is None

    def test_load_returns_stored_value(self, settings, mock_redis_client):
        payload = json.dumps([{"date": "2024-03-15"}])
        mock_redis_client.get.return_value = payload
        with patch("redis.from_url", return_value=mock_redis_client):
            result = rc.load_digest("2024-03-15", settings)
        assert result == payload

    def test_load_uses_correct_key(self, settings, mock_redis_client):
        mock_redis_client.get.return_value = None
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.load_digest("2024-01-01", settings)
        mock_redis_client.get.assert_called_once_with(
            f"{settings.digest_key_prefix}2024-01-01"
        )


class TestUpsertPaper:
    def test_hset_called(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.upsert_paper(
                uid="doi:10.1/abc",
                fields={"title": "Test", "source": "pubmed"},
                embedding=[0.1] * 1536,
                settings=settings,
            )
        assert mock_redis_client.hset.called

    def test_hset_uses_correct_key_prefix(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.upsert_paper(
                uid="testuid",
                fields={"title": "T"},
                embedding=[0.0] * 1536,
                settings=settings,
            )
        call_args = mock_redis_client.hset.call_args
        # The key should start with paper_key_prefix
        all_args = str(call_args)
        assert settings.paper_key_prefix in all_args

    def test_list_fields_serialized_as_json(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.upsert_paper(
                uid="test:1",
                fields={"authors": ["Smith J", "Doe A"]},
                embedding=[0.0] * 1536,
                settings=settings,
            )
        # Get the mapping from hset call
        call_kwargs = mock_redis_client.hset.call_args.kwargs
        mapping = call_kwargs.get("mapping", {})
        if not mapping:
            # positional: hset(name, mapping=...)
            args = mock_redis_client.hset.call_args.args
            mapping = args[1] if len(args) > 1 else {}
        assert "authors" in mapping
        assert json.loads(mapping["authors"]) == ["Smith J", "Doe A"]

    def test_none_fields_become_empty_string(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.upsert_paper(
                uid="test:1",
                fields={"doi": None},
                embedding=[0.0] * 1536,
                settings=settings,
            )
        call_kwargs = mock_redis_client.hset.call_args.kwargs
        mapping = call_kwargs.get("mapping", {})
        if not mapping:
            args = mock_redis_client.hset.call_args.args
            mapping = args[1] if len(args) > 1 else {}
        assert mapping.get("doi") == ""


class TestResetClients:
    def test_reset_clears_cached_client(self, settings, mock_redis_client):
        with patch("redis.from_url", return_value=mock_redis_client):
            rc.get_client(settings)
        assert rc._client is not None
        rc.reset_clients()
        assert rc._client is None

    def test_reset_clears_cached_index(self):
        rc._index = MagicMock()
        rc.reset_clients()
        assert rc._index is None
