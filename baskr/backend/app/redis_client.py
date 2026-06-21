"""Redis connection + RedisVL papers index (SPEC §5.5).

Owns:
- a shared Redis client built from ``Settings.redis_url``
- create/load of the ``baskr:idx:papers`` RedisVL index (HNSW, cosine, dim 1536)
- upsert/query helpers for ``baskr:paper:{uid}`` hashes and digest JSON strings
"""

from __future__ import annotations

import json
from typing import Any

from .config import SETTINGS, Settings

_client: Any = None      # mirror of most-recent client (back-compat)
_index: Any = None       # mirror of most-recent index   (back-compat)
_CLIENTS: dict[str, Any] = {}   # redis_url -> client
_INDEXES: dict[str, Any] = {}   # index name -> SearchIndex


def get_client(settings: Settings = SETTINGS) -> Any:
    """Return a (cached) Redis client for ``settings.redis_url``.

    Socket timeouts are set so a slow/unreachable Redis fails fast instead of
    blocking a request thread indefinitely (e.g. the digest 404 fallback)."""
    global _client
    client = _CLIENTS.get(settings.redis_url)
    if client is None:
        import redis as redis_lib
        client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        _CLIENTS[settings.redis_url] = client
    _client = client
    return client


def ensure_papers_index(settings: Settings = SETTINGS) -> Any:
    """Create the RedisVL HNSW/cosine index (dim ``settings.embed_dim``) if absent;
    return the loaded index handle."""
    global _index
    cached = _INDEXES.get(settings.papers_index)
    if cached is not None:
        _index = cached
        return cached

    from redisvl.index import SearchIndex
    from redisvl.schema import IndexSchema

    schema = IndexSchema.from_dict({
        "index": {
            "name": settings.papers_index,
            "prefix": settings.paper_key_prefix,
            "storage_type": "hash",
        },
        "fields": [
            {"name": "title", "type": "text"},
            {"name": "abstract", "type": "text"},
            {"name": "source", "type": "tag"},
            {"name": "source_id", "type": "tag"},
            {"name": "published", "type": "tag"},
            {"name": "uid", "type": "tag"},
            {"name": "doi", "type": "tag"},
            {"name": "url", "type": "text"},
            {"name": "journal", "type": "text"},
            {
                "name": "embedding",
                "type": "vector",
                "attrs": {
                    "dims": settings.embed_dim,
                    "distance_metric": "cosine",
                    "algorithm": "hnsw",
                    "datatype": "float32",
                },
            },
        ],
    })

    client = get_client(settings)
    index = SearchIndex(schema, redis_client=client)
    index.create(overwrite=False)
    _INDEXES[settings.papers_index] = index
    _index = index
    return index


def upsert_paper(uid: str, fields: dict[str, Any], embedding: list[float],
                 settings: Settings = SETTINGS) -> None:
    """Write a paper hash at ``baskr:paper:{uid}`` and index its embedding."""
    import numpy as np
    client = get_client(settings)
    key = f"{settings.paper_key_prefix}{uid}"
    data: dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, list):
            data[k] = json.dumps(v)
        elif v is None:
            data[k] = ""
        else:
            data[k] = v
    # Persist the canonical uid (the key suffix) as a retrievable field so vector
    # queries can return it even when the caller omits it from ``fields``.
    data.setdefault("uid", uid)
    data["embedding"] = np.array(embedding, dtype=np.float32).tobytes()
    client.hset(key, mapping=data)


# Fields stored as JSON arrays that should be decoded back to lists on read.
_LIST_FIELDS = ("authors", "categories")


def query_similar(embedding: list[float], k: int,
                  settings: Settings = SETTINGS) -> list[dict[str, Any]]:
    """Vector search the papers index; return top-k paper records.

    List-valued fields (authors/categories) are JSON-decoded back to lists."""
    from redisvl.query import VectorQuery
    index = ensure_papers_index(settings)
    query = VectorQuery(
        vector=embedding,
        vector_field_name="embedding",
        return_fields=[
            "title", "abstract", "source", "source_id",
            "published", "uid", "doi", "url", "journal", "authors", "categories",
        ],
        num_results=k,
        dtype="float32",
    )
    results = index.query(query)
    for record in results:
        for field in _LIST_FIELDS:
            val = record.get(field)
            if isinstance(val, str) and val:
                try:
                    record[field] = json.loads(val)
                except (ValueError, TypeError):
                    pass
    return results


def store_digest(date: str, payload: str,
                 settings: Settings = SETTINGS) -> None:
    """Write a frozen digest JSON string to ``baskr:digest:{date}``."""
    client = get_client(settings)
    key = f"{settings.digest_key_prefix}{date}"
    client.set(key, payload)


def load_digest(date: str, settings: Settings = SETTINGS) -> str | None:
    """Read the frozen digest JSON string for ``date`` (or None)."""
    client = get_client(settings)
    key = f"{settings.digest_key_prefix}{date}"
    val = client.get(key)
    if isinstance(val, bytes):
        return val.decode()
    return val


def reset_clients() -> None:
    """Reset cached singletons (used in tests to inject mock clients)."""
    global _client, _index
    _client = None
    _index = None
    _CLIENTS.clear()
    _INDEXES.clear()
