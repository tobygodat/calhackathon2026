"""Redis connection + RedisVL papers index (SPEC §5.5).

Owns:
- a shared Redis client built from ``Settings.redis_url``
- create/load of the ``baskr:idx:papers`` RedisVL index (HNSW, cosine, dim 1536)
- upsert/query helpers for ``baskr:paper:{pmid}`` hashes and digest JSON strings

Scaffold only — bodies raise NotImplementedError.
"""

from __future__ import annotations

from typing import Any

from .config import SETTINGS, Settings


def get_client(settings: Settings = SETTINGS) -> Any:
    """Return a (cached) Redis client for ``settings.redis_url``."""
    raise NotImplementedError


def ensure_papers_index(settings: Settings = SETTINGS) -> Any:
    """Create the RedisVL HNSW/cosine index (dim ``settings.embed_dim``) if absent;
    return the loaded index handle."""
    raise NotImplementedError


def upsert_paper(uid: str, fields: dict[str, Any], embedding: list[float]) -> None:
    """Write a paper hash at ``baskr:paper:{uid}`` and index its embedding."""
    raise NotImplementedError


def query_similar(embedding: list[float], k: int) -> list[dict[str, Any]]:
    """Vector search the papers index; return top-k paper records."""
    raise NotImplementedError


def store_digest(date: str, payload: str) -> None:
    """Write a frozen digest JSON string to ``baskr:digest:{date}``."""
    raise NotImplementedError


def load_digest(date: str) -> str | None:
    """Read the frozen digest JSON string for ``date`` (or None)."""
    raise NotImplementedError
