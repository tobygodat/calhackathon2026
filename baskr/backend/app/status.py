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


def _probe_redisvl(settings: Settings) -> dict[str, Any]:
    """Does the papers index exist? Report doc count in ``detail``."""
    from .redis_client import ensure_papers_index  # noqa: PLC0415

    index = ensure_papers_index(settings)
    info = index.info()
    docs = int(info.get("num_docs", 0))
    return {"ok": True, "detail": f"{docs} docs", "num_docs": docs}


def _probe_streams(settings: Settings) -> dict[str, Any]:
    """XLEN of the new-papers stream."""
    from .streams import NEW_PAPERS_STREAM, stream_length  # noqa: PLC0415

    length = stream_length(settings)
    return {"ok": True, "detail": f"{NEW_PAPERS_STREAM}={length}", "stream_length": length}


def _probe_agent_memory(settings: Settings) -> dict[str, Any]:
    """Profile item count in the lab Agent Memory namespace."""
    from .memory import profile_item_count  # noqa: PLC0415

    count = profile_item_count(settings)
    return {"ok": True, "detail": f"{count} items", "memory_records": count}


def _probe_langcache(settings: Settings) -> dict[str, Any]:
    """LangCache reachability + tracked hit-rate (Redis-backed stub)."""
    from .langcache import stats  # noqa: PLC0415

    s = stats(settings)
    return {"ok": True, "detail": f"hit_rate={s['hit_rate']}", "hit_rate": s["hit_rate"]}


def _probe_consumer() -> dict[str, Any]:
    """Check whether the background stream consumer is alive."""
    from . import consumer as _consumer  # noqa: PLC0415

    hb = _consumer.last_heartbeat()
    if hb is None:
        return {"ok": False, "status": "unknown", "detail": "not started"}
    import datetime  # noqa: PLC0415

    try:
        ts = datetime.datetime.fromisoformat(hb.replace("Z", "+00:00"))
        age_s = (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds()
        if age_s <= 10:
            return {"ok": True, "detail": f"heartbeat {age_s:.1f}s ago"}
        return {"ok": False, "status": "degraded", "detail": f"heartbeat {age_s:.0f}s ago (stale)"}
    except Exception:  # noqa: BLE001
        return {"ok": True, "detail": f"last heartbeat: {hb}"}


def _probe_key_present(value: str | None) -> dict[str, Any]:
    """Presence-only probe for an API-key-gated service.

    Deliberately makes NO network call: ``/status`` is polled frequently and a paid
    embeddings/messages round-trip per poll would burn tokens. Presence of the key
    is reported as ``configured``; absence as ``not configured`` (degraded mode —
    the embeddings/LLM layers still run via their deterministic fallbacks).
    """
    if value:
        return {"ok": True, "status": "configured"}
    return {"ok": False, "status": "not configured", "detail": "no API key; using degraded fallback"}


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

    # Per-feature probes hit Redis directly; gate them on basic reachability so a
    # downed Redis doesn't stall each probe on its own timeout.
    def _gated(probe) -> dict[str, Any]:
        if not redis_ok:
            return {"ok": False, "status": "unknown", "detail": "redis unavailable"}
        return _safe(probe, settings)

    return {
        "redis": redis_status,
        "redisvl": _gated(_probe_redisvl),
        "streams": _gated(_probe_streams),
        "agent_memory": _gated(_probe_agent_memory),
        "langcache": _gated(_probe_langcache),
        "openai": _safe(_probe_key_present, settings.openai_api_key),
        "anthropic": _safe(_probe_key_present, settings.anthropic_api_key),
        # PubMed needs no key (NCBI key only raises rate limits); reachable by default.
        "pubmed": {"ok": True, "status": "unknown"},
        # Consumer: ok if heartbeat is fresh (updated within 10 s).
        "consumer": _probe_consumer(),
    }


def _safe_int(probe, settings: Settings, default: int = 0) -> int:
    """Run a counter probe, degrading any error to ``default``."""
    try:
        return int(probe(settings))
    except Exception:  # noqa: BLE001  (metrics never raise)
        return default


def _safe_float(probe, settings: Settings, default: float = 0.0) -> float:
    try:
        return float(probe(settings))
    except Exception:  # noqa: BLE001
        return default


def _consumer_heartbeat() -> str | None:
    try:
        from . import consumer as _consumer  # noqa: PLC0415
        return _consumer.last_heartbeat()
    except Exception:  # noqa: BLE001
        return None


def _consumer_alerts_fired() -> int:
    try:
        from . import consumer as _consumer  # noqa: PLC0415
        return _consumer.alerts_fired_count()
    except Exception:  # noqa: BLE001
        return 0


def build_metrics(settings: Settings = SETTINGS) -> dict[str, Any]:
    """Pipeline metrics. Redis-backed counters are now real (Phase 1); the
    agent-loop counters (papers processed / alerts / heartbeats) stay stubbed until
    the consumer wires in (Phase 6)."""
    from .langcache import stats as _langcache_stats  # noqa: PLC0415
    from .memory import profile_item_count  # noqa: PLC0415
    from .redis_client import ensure_papers_index  # noqa: PLC0415
    from .streams import stream_length  # noqa: PLC0415

    corpus_index_docs = _safe_int(
        lambda s: ensure_papers_index(s).info().get("num_docs", 0), settings
    )
    stream_len = _safe_int(stream_length, settings)
    memory_records = _safe_int(profile_item_count, settings)
    langcache_hit_rate = _safe_float(
        lambda s: _langcache_stats(s)["hit_rate"], settings
    )

    from . import pipeline_state  # noqa: PLC0415  (lazy: avoid circular at import)

    ps = pipeline_state.get()
    return {
        "papers_processed_last_hour": 0,
        "papers_processed_total": 0,
        "corpus_index_docs": corpus_index_docs,
        "stream_length": stream_len,
        "stream_pending": 0,
        "memory_records": memory_records,
        "langcache_hit_rate": langcache_hit_rate,
        "last_processed_at": None,
        "consumer_last_heartbeat": _consumer_heartbeat(),
        "alerts_fired_last_hour": _consumer_alerts_fired(),
        # Pipeline-specific metrics (updated by POST /api/pipeline/search).
        "pipeline_source_counts": ps.get("pipeline_source_counts"),
        "pipeline_dedupe_ratio": ps.get("pipeline_dedupe_ratio"),
        "pipeline_last_query": ps.get("pipeline_last_query"),
        "pipeline_last_result_count": ps.get("pipeline_last_result_count"),
        "pipeline_source_errors": ps.get("pipeline_source_errors"),
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
