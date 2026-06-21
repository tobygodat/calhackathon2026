"""LangCache surface: a Redis-backed semantic-cache stub (SPEC §5.5).

The spec calls for a managed LangCache (semantic cache of query results). No managed
LangCache exists in this environment, so Phase 1 ships a **Redis-backed stub** behind
get/set keyed by a hash of the (normalized) query string. This is an *exact-match*
cache, not yet semantic — it stores under ``baskr:langcache:{sha1(query)}`` and tracks
hit/miss counters so /status can surface a real hit-rate. Phase 2+ upgrades the key to
a semantic (embedding nearest-neighbour) lookup behind these same signatures.
"""

from __future__ import annotations

import hashlib

from .config import SETTINGS, Settings
from .redis_client import get_client

_CACHE_PREFIX = "baskr:langcache:"
_HITS_KEY = "baskr:langcache:stats:hits"
_MISSES_KEY = "baskr:langcache:stats:misses"


def _cache_key(query: str) -> str:
    digest = hashlib.sha1(query.strip().lower().encode()).hexdigest()
    return f"{_CACHE_PREFIX}{digest}"


def get(query: str, settings: Settings = SETTINGS) -> str | None:
    """Return a cached result payload for ``query`` (or None); records hit/miss."""
    client = get_client(settings)
    raw = client.get(_cache_key(query))
    if raw is None:
        client.incr(_MISSES_KEY)
        return None
    client.incr(_HITS_KEY)
    return raw.decode() if isinstance(raw, bytes) else raw


def set(query: str, payload: str, ttl: int | None = None,
        settings: Settings = SETTINGS) -> None:
    """Cache ``payload`` for ``query`` (optional TTL seconds)."""
    client = get_client(settings)
    client.set(_cache_key(query), payload, ex=ttl)


def stats(settings: Settings = SETTINGS) -> dict[str, float | int]:
    """Hit/miss counters + hit-rate for /status (langcache_hit_rate)."""
    client = get_client(settings)

    def _int(value: object) -> int:
        if value is None:
            return 0
        return int(value.decode() if isinstance(value, bytes) else value)

    hits = _int(client.get(_HITS_KEY))
    misses = _int(client.get(_MISSES_KEY))
    total = hits + misses
    hit_rate = round(hits / total, 4) if total else 0.0
    return {"hits": hits, "misses": misses, "hit_rate": hit_rate}
