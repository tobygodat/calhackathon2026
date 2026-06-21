"""Health / status probing for ``GET /status`` (dev-ui dashboard).

The dashboard (see ``dev-ui/README.md``) polls ``/status`` and renders connection
badges plus pipeline metrics. This module assembles that exact payload shape while
running in DEGRADED MODE: every probe is wrapped so it can NEVER raise. When a
dependency is unconfigured (no API key) or unreachable (no Redis), the probe reports
``ok: false`` / ``status: "unknown"`` rather than crashing the handler.

Payload shape (top-level keys):
    healthy        bool          -- all monitored connections OK
    connections    dict[str,..]  -- per-service {ok, latency_ms?, detail?, status?}
    metrics        dict          -- pipeline counters (degraded -> 0 / null)
    redis_sources  list[str]     -- Redis features in play

Real metric wiring lands in later phases; for now metrics are best-effort/stubbed.
"""

from __future__ import annotations

import time
from typing import Any

from .config import SETTINGS, Settings

# Connections that count toward the "healthy" rollup and the dashboard's
# "connections healthy %" metric.
_CONNECTION_KEYS = (
    "redis",
    "redisvl",
    "streams",
    "agent_memory",
    "langcache",
    "openai",
    "anthropic",
    "pubmed",
    "consumer",
)

_REDIS_SOURCES = ["RedisVL", "Streams", "Agent Memory", "LangCache"]


def _probe_redis(settings: Settings) -> dict[str, Any]:
    """Ping Redis. Lazy import so a missing ``redis`` package never breaks boot."""
    start = time.perf_counter()
    try:
        import redis  # noqa: PLC0415  (lazy: keep app boot light / degraded-safe)

        client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
        )
        client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        return {"ok": True, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001  (never raise out of a probe)
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:200]}


def _probe_key_present(value: str | None) -> dict[str, Any]:
    """Presence-only probe for an API-key-gated service (no network call)."""
    if value:
        return {"ok": True, "status": "configured"}
    return {"ok": False, "status": "unknown", "detail": "not configured"}


def _safe(probe, *args: Any) -> dict[str, Any]:
    """Run a probe, degrading any unexpected error into an ``ok: false`` entry."""
    try:
        return probe(*args)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "unknown", "detail": f"{type(exc).__name__}: {exc}"[:200]}


def build_connections(settings: Settings = SETTINGS) -> dict[str, dict[str, Any]]:
    """Probe every monitored connection. Never raises."""
    redis_status = _safe(_probe_redis, settings)
    redis_ok = bool(redis_status.get("ok"))

    # RedisVL / Streams / Agent Memory / LangCache all ride on the Redis
    # connection; their real readiness checks land in later phases. For now they
    # inherit Redis reachability so the dashboard reflects the live dependency.
    redis_backed = (
        {"ok": True, "status": "unknown"}
        if redis_ok
        else {"ok": False, "status": "unknown", "detail": "redis unavailable"}
    )

    return {
        "redis": redis_status,
        "redisvl": dict(redis_backed),
        "streams": dict(redis_backed),
        "agent_memory": dict(redis_backed),
        "langcache": dict(redis_backed),
        "openai": _safe(_probe_key_present, settings.openai_api_key),
        "anthropic": _safe(_probe_key_present, settings.anthropic_api_key),
        # PubMed needs no key (NCBI key only raises rate limits); reachable by default.
        "pubmed": {"ok": True, "status": "unknown"},
        # No background consumer running yet (Phase 0); report not-yet-up.
        "consumer": {"ok": False, "status": "unknown", "detail": "not running"},
    }


def build_metrics(settings: Settings = SETTINGS) -> dict[str, Any]:
    """Pipeline metrics. Degraded defaults until real wiring lands (later phases)."""
    return {
        "papers_processed_last_hour": 0,
        "papers_processed_total": 0,
        "alerts_fired_last_hour": 0,
        "corpus_index_docs": 0,
        "stream_length": 0,
        "stream_pending": 0,
        "memory_records": 0,
        "langcache_hit_rate": 0.0,
        "last_processed_at": None,
        "consumer_last_heartbeat": None,
    }


def get_status(settings: Settings = SETTINGS) -> dict[str, Any]:
    """Assemble the full ``/status`` payload. Guaranteed never to raise."""
    try:
        connections = build_connections(settings)
    except Exception:  # noqa: BLE001  (defence in depth)
        connections = {k: {"ok": False, "status": "unknown"} for k in _CONNECTION_KEYS}

    try:
        metrics = build_metrics(settings)
    except Exception:  # noqa: BLE001
        metrics = {}

    healthy = bool(connections) and all(
        conn.get("ok") for conn in connections.values()
    )

    return {
        "healthy": healthy,
        "connections": connections,
        "metrics": metrics,
        "redis_sources": list(_REDIS_SOURCES),
    }
