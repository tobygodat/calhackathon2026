"""Redis connection + RedisVL papers index (SPEC §5.5).

Owns:
- a shared Redis client built from ``Settings.redis_url``
- create/load of the ``baskr:idx:papers`` RedisVL index (HNSW, cosine, dim 1536)
- upsert/query helpers for ``baskr:paper:{pmid}`` hashes and digest JSON strings

Implementation notes (Phase 1):
- The index is built with **RedisVL** (``SearchIndex`` + an explicit schema dict),
  HNSW / COSINE / dim ``settings.embed_dim``. This is the primary path and runs
  whenever the Redis server exposes the RediSearch module.
- Embeddings ride as a ``float32`` byte blob in the hash field ``embedding``;
  the schema declares it as the vector field.
- Paper metadata fields mirror ``PaperOut`` (list fields are stored as ``|``-joined
  TAG strings so they survive the hash round-trip).
- **Fallback:** when the live Redis lacks RediSearch (e.g. a vanilla ``redis-server``
  with no module, as in this sandbox where redis-stack/Docker layers are
  unreachable), ``ensure_papers_index`` transparently degrades to a pure-Python
  brute-force cosine scan over the ``baskr:paper:*`` hashes. Same signatures, same
  results ordering; it just doesn't use the server-side ANN index. The moment a
  search-capable Redis is present the RedisVL path is used automatically.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from .config import SETTINGS, Settings

# Hash field that carries the raw float32 embedding blob.
_VECTOR_FIELD = "embedding"
# PaperOut list fields are flattened to delimited strings for hash storage.
_LIST_FIELDS = ("authors", "categories")
_LIST_DELIM = "|"

# Sentinel handle returned by ensure_papers_index when RediSearch is unavailable
# and the brute-force fallback is in effect.
class _FallbackIndex:
    """Minimal SearchIndex-shaped handle for the brute-force fallback path."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.name = settings.papers_index

    def exists(self) -> bool:
        return True  # brute-force scan needs no server-side index

    def create(self, *args: Any, **kwargs: Any) -> None:  # no-op
        return None

    def info(self) -> dict[str, Any]:
        client = get_client(self._settings)
        keys = client.keys(f"{self._settings.paper_key_prefix}*")
        return {"num_docs": len(keys), "backend": "brute_force"}


# Module-level singletons keyed by redis_url so distinct settings get distinct clients.
_CLIENTS: dict[str, Any] = {}
_INDEXES: dict[str, Any] = {}


def _redisearch_available(settings: Settings) -> bool:
    """True if the live Redis exposes the RediSearch module (FT.* commands)."""
    try:
        get_client(settings).execute_command("FT._LIST")
        return True
    except Exception:  # noqa: BLE001  (ResponseError 'unknown command' etc.)
        return False


def get_client(settings: Settings = SETTINGS) -> Any:
    """Return a (cached) Redis client for ``settings.redis_url``.

    Lazy singleton: built on first use, reused thereafter. ``decode_responses`` is
    left False so embedding byte blobs survive untouched; metadata is decoded
    explicitly where needed.
    """
    import redis  # noqa: PLC0415  (lazy: keep import light / degraded-safe)

    url = settings.redis_url
    client = _CLIENTS.get(url)
    if client is None:
        client = redis.Redis.from_url(url)
        _CLIENTS[url] = client
    return client


def _papers_schema(settings: Settings) -> dict[str, Any]:
    """RedisVL schema dict for the papers index (HNSW, cosine, dim embed_dim)."""
    prefix = settings.paper_key_prefix.rstrip(":")
    return {
        "index": {
            "name": settings.papers_index,
            "prefix": prefix,
            "key_separator": ":",
            "storage_type": "hash",
        },
        "fields": [
            {"name": "uid", "type": "tag"},
            {"name": "source", "type": "tag"},
            {"name": "source_id", "type": "tag"},
            {"name": "title", "type": "text"},
            {"name": "abstract", "type": "text"},
            {"name": "authors", "type": "tag", "attrs": {"separator": _LIST_DELIM}},
            {"name": "categories", "type": "tag", "attrs": {"separator": _LIST_DELIM}},
            {"name": "doi", "type": "tag"},
            {"name": "url", "type": "tag"},
            {"name": "journal", "type": "tag"},
            {"name": "published", "type": "tag"},
            {
                "name": _VECTOR_FIELD,
                "type": "vector",
                "attrs": {
                    "dims": settings.embed_dim,
                    "algorithm": "hnsw",
                    "distance_metric": "cosine",
                    "datatype": "float32",
                },
            },
        ],
    }


def ensure_papers_index(settings: Settings = SETTINGS) -> Any:
    """Create the RedisVL HNSW/cosine index (dim ``settings.embed_dim``) if absent;
    return the loaded index handle.

    Idempotent: creating an existing index is a no-op (``overwrite=False``), and the
    handle is cached per redis_url so repeated calls are cheap.
    """
    url = settings.redis_url
    index = _INDEXES.get(url)
    if index is not None:
        return index

    if not _redisearch_available(settings):
        index = _FallbackIndex(settings)
        _INDEXES[url] = index
        return index

    from redisvl.index import SearchIndex  # noqa: PLC0415

    index = SearchIndex.from_dict(_papers_schema(settings), redis_client=get_client(settings))
    # overwrite=False keeps an existing index intact -> create-twice is safe.
    if not index.exists():
        index.create(overwrite=False)
    _INDEXES[url] = index
    return index


def _to_float32_bytes(embedding: list[float]) -> bytes:
    """Pack a float list into a little-endian float32 blob (RedisVL hash storage)."""
    return struct.pack(f"<{len(embedding)}f", *embedding)


def _flatten_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Coerce a PaperOut-shaped dict into hash-safe scalars (lists -> delimited str)."""
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key in _LIST_FIELDS and isinstance(value, (list, tuple)):
            out[key] = _LIST_DELIM.join(str(v) for v in value)
        else:
            out[key] = value
    return out


def _inflate_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Decode a RedisVL/HASH record back into a PaperOut-ish dict.

    Drops the raw vector blob and re-splits delimited list fields.
    """
    record: dict[str, Any] = {}
    for key, value in raw.items():
        name = key.decode() if isinstance(key, bytes) else key
        if name == _VECTOR_FIELD:
            continue
        if isinstance(value, bytes):
            try:
                value = value.decode()
            except UnicodeDecodeError:
                continue  # leftover binary (e.g. vector) -> skip
        if name in _LIST_FIELDS:
            value = value.split(_LIST_DELIM) if value else []
        record[name] = value
    return record


def upsert_paper(uid: str, fields: dict[str, Any], embedding: list[float],
                 settings: Settings = SETTINGS) -> None:
    """Write a paper hash at ``baskr:paper:{uid}`` and index its embedding."""
    ensure_papers_index(settings)
    key = f"{settings.paper_key_prefix}{uid}"
    mapping = _flatten_fields(fields)
    mapping["uid"] = uid
    mapping[_VECTOR_FIELD] = _to_float32_bytes(embedding)
    get_client(settings).hset(key, mapping=mapping)


def query_similar(embedding: list[float], k: int,
                  settings: Settings = SETTINGS) -> list[dict[str, Any]]:
    """Vector search the papers index; return top-k paper records (as dicts).

    Each record carries the PaperOut metadata plus a ``vector_distance`` score
    (cosine distance; smaller = nearer).
    """
    index = ensure_papers_index(settings)

    if isinstance(index, _FallbackIndex):
        return _query_similar_brute_force(embedding, k, settings)

    from redisvl.query import VectorQuery  # noqa: PLC0415

    return_fields = [
        "uid", "source", "source_id", "title", "abstract",
        "authors", "categories", "doi", "url", "journal", "published",
    ]
    query = VectorQuery(
        vector=embedding,
        vector_field_name=_VECTOR_FIELD,
        return_fields=return_fields,
        num_results=k,
        dtype="float32",
    )
    results = index.query(query)
    return [_inflate_record(row) for row in results]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine *distance* (1 - cosine similarity); matches RediSearch COSINE metric."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return 1.0 - (dot / (na * nb))


def _query_similar_brute_force(embedding: list[float], k: int,
                               settings: Settings) -> list[dict[str, Any]]:
    """Pure-Python KNN scan over ``baskr:paper:*`` hashes (RediSearch-less fallback)."""
    client = get_client(settings)
    scored: list[tuple[float, dict[str, Any]]] = []
    for key in client.keys(f"{settings.paper_key_prefix}*"):
        raw = client.hgetall(key)
        blob = raw.get(_VECTOR_FIELD.encode()) or raw.get(_VECTOR_FIELD)
        if not blob:
            continue
        count = len(blob) // 4
        vec = list(struct.unpack(f"<{count}f", blob))
        dist = _cosine_distance(embedding, vec)
        record = _inflate_record(raw)
        record["vector_distance"] = dist
        scored.append((dist, record))
    scored.sort(key=lambda pair: pair[0])
    return [record for _, record in scored[:k]]


def store_digest(date: str, payload: str, settings: Settings = SETTINGS) -> None:
    """Write a frozen digest JSON string to ``baskr:digest:{date}``."""
    key = f"{settings.digest_key_prefix}{date}"
    get_client(settings).set(key, payload)


def load_digest(date: str, settings: Settings = SETTINGS) -> str | None:
    """Read the frozen digest JSON string for ``date`` (or None)."""
    key = f"{settings.digest_key_prefix}{date}"
    raw = get_client(settings).get(key)
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else raw
