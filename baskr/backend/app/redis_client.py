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

_client: Any = None
_index: Any = None


def get_client(settings: Settings = SETTINGS) -> Any:
    """Return a (cached) Redis client for ``settings.redis_url``."""
    global _client
    if _client is None:
        import redis as redis_lib
        _client = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _client


def ensure_papers_index(settings: Settings = SETTINGS) -> Any:
    """Create the RedisVL HNSW/cosine index (dim ``settings.embed_dim``) if absent;
    return the loaded index handle."""
    global _index
    if _index is not None:
        return _index

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
    _index = index
    return _index


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
    data["embedding"] = np.array(embedding, dtype=np.float32).tobytes()
    client.hset(key, mapping=data)


def query_similar(embedding: list[float], k: int,
                  settings: Settings = SETTINGS) -> list[dict[str, Any]]:
    """Vector search the papers index; return top-k paper records."""
    from redisvl.query import VectorQuery
    index = ensure_papers_index(settings)
    query = VectorQuery(
        vector=embedding,
        vector_field_name="embedding",
        return_fields=[
            "title", "abstract", "source", "source_id",
            "published", "uid", "doi", "url", "journal",
        ],
        num_results=k,
        dtype="float32",
    )
    return index.query(query)


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
    return client.get(key)


def reset_clients() -> None:
    """Reset cached singletons (used in tests to inject mock clients)."""
    global _client, _index
    _client = None
    _index = None
