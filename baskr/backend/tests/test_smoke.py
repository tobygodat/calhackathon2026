"""Phase 0 smoke tests: app imports, health endpoint, and /status shape."""

from __future__ import annotations


def test_app_main_imports() -> None:
    """(a) ``import app.main`` must succeed with no ImportError/NotImplementedError."""
    import app.main  # noqa: F401


def test_health_ok(client) -> None:
    """(b) GET /api/health returns exactly {"status": "ok"}."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# Connection sub-keys documented in dev-ui/README.md.
_CONNECTION_KEYS = {
    "redis",
    "redisvl",
    "streams",
    "agent_memory",
    "langcache",
    "openai",
    "anthropic",
    "pubmed",
    "consumer",
}

# Metric sub-keys documented in dev-ui/README.md.
_METRIC_KEYS = {
    "papers_processed_last_hour",
    "papers_processed_total",
    "alerts_fired_last_hour",
    "corpus_index_docs",
    "stream_length",
    "stream_pending",
    "memory_records",
    "langcache_hit_rate",
    "last_processed_at",
    "consumer_last_heartbeat",
}


def test_status_shape(client) -> None:
    """(c) GET /status returns 200 with the documented top-level + sub keys."""
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.json()

    # Top-level keys.
    assert set(body.keys()) == {"healthy", "connections", "metrics", "redis_sources"}
    assert isinstance(body["healthy"], bool)
    assert isinstance(body["redis_sources"], list)

    # Connection sub-keys, each an object with an ``ok`` boolean.
    connections = body["connections"]
    assert _CONNECTION_KEYS <= set(connections.keys())
    for name in _CONNECTION_KEYS:
        assert isinstance(connections[name], dict)
        assert isinstance(connections[name]["ok"], bool)

    # Metric sub-keys.
    assert _METRIC_KEYS <= set(body["metrics"].keys())


def test_status_never_raises_when_redis_down() -> None:
    """The probe degrades gracefully when Redis is unreachable."""
    from app.config import Settings
    from app.status import get_status

    settings = Settings(redis_url="redis://127.0.0.1:6390")  # nothing listening
    payload = get_status(settings)
    assert payload["connections"]["redis"]["ok"] is False
    assert payload["healthy"] is False
