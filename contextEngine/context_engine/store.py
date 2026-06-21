"""Vector store for context items.

Two backends behind one interface (``add`` / ``search`` / ``all`` / ``clear``):

- **LocalStore** (default): items + L2-normalized vectors persisted to a JSON
  file and a numpy ``.npy`` file under ``settings.store_path``. Cosine similarity
  is a single matmul. Needs no infra — ideal for dev, demos, and tests.
- **RedisStore** (``CONTEXT_STORE=redis``): a RediSearch HNSW vector index over
  hash documents, with a TAG filter on item ``kind`` for hybrid search.

``get_store(settings)`` returns the configured backend, transparently falling
back to LocalStore if Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import SETTINGS, Settings
from .models import ContextItem, ItemKind

log = logging.getLogger("context_engine.store")


class SearchHit:
    """A retrieved item plus its cosine similarity to the query."""

    __slots__ = ("item", "score")

    def __init__(self, item: ContextItem, score: float):
        self.item = item
        self.score = score

    def to_dict(self) -> dict:
        d = self.item.to_dict()
        d["score"] = round(self.score, 4)
        return d


def _to_item(d: dict) -> ContextItem:
    prov = d.get("provenance", [])
    if isinstance(prov, str):  # Redis/Iris round-trip stores it joined
        prov = [p for p in prov.split("\n") if p]
    return ContextItem(
        kind=ItemKind.coerce(d.get("kind", "finding")),
        text=d.get("text", ""),
        evidence=d.get("evidence", ""),
        source_id=d.get("source_id", ""),
        source_title=d.get("source_title", ""),
        confidence=float(d.get("confidence", 0.0) or 0.0),
        id=d.get("id", ""),
        created_at=float(d.get("created_at", 0.0) or 0.0),
        version=int(d.get("version", 1) or 1),
        status=d.get("status", "active") or "active",
        supersedes=d.get("supersedes") or None,
        provenance=prov,
    )


class LocalStore:
    """File-backed numpy vector store. Vectors are stored L2-normalized."""

    def __init__(self, settings: Settings = SETTINGS):
        self.dim = settings.embed_dim
        base = Path(settings.store_path)
        base.mkdir(parents=True, exist_ok=True)
        self._meta_path = base / "items.json"
        self._vec_path = base / "vectors.npy"
        self._meta: list[dict] = []
        self._load()

    def _load(self) -> None:
        import numpy as np

        if self._meta_path.exists():
            self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
        if self._vec_path.exists():
            self._vecs = np.load(self._vec_path)
        else:
            self._vecs = np.zeros((0, self.dim), dtype=np.float32)

    def _persist(self) -> None:
        import numpy as np

        self._meta_path.write_text(json.dumps(self._meta, ensure_ascii=False), encoding="utf-8")
        np.save(self._vec_path, self._vecs)

    def add(self, items: list[ContextItem]) -> int:
        """Add items (each must carry an embedding). Skips ids already present."""
        import numpy as np

        existing = {m["id"] for m in self._meta}
        new_meta, new_vecs = [], []
        for it in items:
            if it.embedding is None or it.id in existing:
                continue
            existing.add(it.id)
            new_meta.append(it.to_dict())
            v = np.asarray(it.embedding, dtype=np.float32)
            n = float(np.linalg.norm(v))
            new_vecs.append(v / n if n > 0 else v)
        if not new_meta:
            return 0
        self._meta.extend(new_meta)
        self._vecs = np.vstack([self._vecs, np.asarray(new_vecs, dtype=np.float32)])
        self._persist()
        return len(new_meta)

    def get(self, item_id: str) -> ContextItem | None:
        for m in self._meta:
            if m["id"] == item_id:
                return _to_item(m)
        return None

    def update(self, item: ContextItem) -> bool:
        """Replace an existing item's metadata (and vector, if re-embedded) in place.

        Used by the revision layer for nuance/merge edits and status changes. The
        id is preserved; only this row is touched.
        """
        import numpy as np

        for i, m in enumerate(self._meta):
            if m["id"] != item.id:
                continue
            self._meta[i] = item.to_dict()
            if item.embedding is not None:
                v = np.asarray(item.embedding, dtype=np.float32)
                n = float(np.linalg.norm(v))
                self._vecs[i] = v / n if n > 0 else v
            self._persist()
            return True
        return False

    def search(
        self, query_text: str, vector: list[float], top_k: int,
        kind: ItemKind | None = None,
    ) -> list[SearchHit]:
        import numpy as np

        if len(self._meta) == 0:
            return []
        q = np.asarray(vector, dtype=np.float32)
        n = float(np.linalg.norm(q))
        if n > 0:
            q = q / n
        sims = self._vecs @ q  # cosine, both sides normalized
        order = np.argsort(-sims)
        hits: list[SearchHit] = []
        for i in order:
            meta = self._meta[int(i)]
            if kind is not None and meta.get("kind") != kind.value:
                continue
            hits.append(SearchHit(_to_item(meta), float(sims[int(i)])))
            if len(hits) >= top_k:
                break
        return hits

    def all(self, kind: ItemKind | None = None) -> list[ContextItem]:
        return [
            _to_item(m) for m in self._meta
            if kind is None or m.get("kind") == kind.value
        ]

    def clear(self) -> None:
        import numpy as np

        self._meta = []
        self._vecs = np.zeros((0, self.dim), dtype=np.float32)
        self._persist()


class RedisStore:
    """RediSearch HNSW vector index over hash docs, with a kind TAG filter."""

    def __init__(self, settings: Settings):
        import redis

        self.settings = settings
        self.dim = settings.embed_dim
        self.r = redis.Redis.from_url(settings.redis_url, decode_responses=False)
        self.r.ping()
        self._ensure_index()

    def _ensure_index(self) -> None:
        from redis.commands.search.field import TagField, TextField, VectorField
        from redis.commands.search.indexDefinition import IndexDefinition, IndexType

        s = self.settings
        try:
            self.r.ft(s.items_index).info()
            return  # already exists
        except Exception:  # noqa: BLE001 - not created yet
            pass
        schema = (
            TagField("kind"),
            TextField("text"),
            TextField("source_id"),
            VectorField(
                "embedding", "HNSW",
                {"TYPE": "FLOAT32", "DIM": self.dim, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        definition = IndexDefinition(prefix=[s.item_key_prefix], index_type=IndexType.HASH)
        self.r.ft(s.items_index).create_index(schema, definition=definition)

    def add(self, items: list[ContextItem]) -> int:
        import numpy as np

        s = self.settings
        added = 0
        pipe = self.r.pipeline()
        for it in items:
            if it.embedding is None:
                continue
            v = np.asarray(it.embedding, dtype=np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            pipe.hset(f"{s.item_key_prefix}{it.id}", mapping=self._mapping(it, v))
            added += 1
        pipe.execute()
        return added

    @staticmethod
    def _mapping(it: ContextItem, vec) -> dict:
        return {
            "kind": it.kind.value,
            "text": it.text,
            "evidence": it.evidence,
            "source_id": it.source_id,
            "source_title": it.source_title,
            "confidence": str(it.confidence),
            "created_at": str(it.created_at),
            "version": str(it.version),
            "status": it.status,
            "supersedes": it.supersedes or "",
            "provenance": "\n".join(it.provenance),
            "embedding": vec.tobytes(),
        }

    _FIELDS = ("kind", "text", "evidence", "source_id", "source_title",
               "confidence", "created_at", "version", "status", "supersedes",
               "provenance")

    def get(self, item_id: str) -> ContextItem | None:
        h = self.r.hgetall(f"{self.settings.item_key_prefix}{item_id}")
        if not h:
            return None
        d = {_dec(k): _dec(val) for k, val in h.items()}
        d["id"] = item_id
        return _to_item(d)

    def update(self, item: ContextItem) -> bool:
        import numpy as np

        key = f"{self.settings.item_key_prefix}{item.id}"
        if not self.r.exists(key):
            return False
        v = np.asarray(item.embedding, dtype=np.float32) if item.embedding else None
        if v is not None:
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
        else:  # text unchanged: preserve the existing vector
            v = np.frombuffer(self.r.hget(key, "embedding"), dtype=np.float32)
        self.r.hset(key, mapping=self._mapping(item, v))
        return True

    def search(
        self, query_text: str, vector: list[float], top_k: int,
        kind: ItemKind | None = None,
    ) -> list[SearchHit]:
        import numpy as np
        from redis.commands.search.query import Query

        v = np.asarray(vector, dtype=np.float32)
        n = float(np.linalg.norm(v))
        if n > 0:
            v = v / n
        prefilter = f"@kind:{{{kind.value}}}" if kind else "*"
        q = (
            Query(f"({prefilter})=>[KNN {top_k} @embedding $vec AS score]")
            .sort_by("score")
            .return_fields(*self._FIELDS, "score")
            .dialect(2)
        )
        res = self.r.ft(self.settings.items_index).search(
            q, query_params={"vec": v.tobytes()}
        )
        hits: list[SearchHit] = []
        for doc in res.docs:
            d = {k: _dec(getattr(doc, k, "")) for k in self._FIELDS}
            d["id"] = doc.id.split(self.settings.item_key_prefix)[-1]
            # Redis returns cosine DISTANCE; similarity = 1 - distance.
            score = 1.0 - float(_dec(getattr(doc, "score", "1")))
            hits.append(SearchHit(_to_item(d), score))
        return hits

    def all(self, kind: ItemKind | None = None) -> list[ContextItem]:
        from redis.commands.search.query import Query

        prefilter = f"@kind:{{{kind.value}}}" if kind else "*"
        q = Query(prefilter).paging(0, 10000).return_fields(*self._FIELDS)
        res = self.r.ft(self.settings.items_index).search(q)
        out = []
        for doc in res.docs:
            d = {k: _dec(getattr(doc, k, "")) for k in self._FIELDS}
            d["id"] = doc.id.split(self.settings.item_key_prefix)[-1]
            out.append(_to_item(d))
        return out

    def clear(self) -> None:
        keys = list(self.r.scan_iter(match=f"{self.settings.item_key_prefix}*"))
        if keys:
            self.r.delete(*keys)


def _dec(v):
    return v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else v


# Sentinel separating the human belief text from its JSON payload inside an Iris
# record's single `text` field. Iris has no free metadata slot, so the structured
# fields ride along after this marker and are stripped back out on read. Only the
# belief (before the marker) is what the user/search reads; topics carry the
# filterable state (kind/status) so we never hide *filterable* signals in text.
_TRAILER = "\n␞␞CTXMETA␞␞\n"


class IrisStore:
    """Redis Agent Memory (Iris RAM) as a durable, evolving belief store.

    Each ContextItem is one long-term memory: ``text`` = belief + JSON trailer,
    ``topics`` = filterable state (``kind:*``, ``status:*``), scoped by ``owner_id``
    + ``namespace``. Revision edits go through ``update_long_term_memory`` so a
    belief keeps its id as it evolves. Iris returns no per-item score, so
    ``search`` re-ranks candidates with our own embedder for a transparent cosine.
    """

    def __init__(self, settings: Settings):
        from redis_agent_memory import AgentMemory  # noqa: PLC0415

        if not (settings.iris_base_url and settings.iris_store_id and settings.iris_api_key):
            raise RuntimeError("Iris RAM credentials not configured")
        self.settings = settings
        self.am = AgentMemory(
            settings.iris_base_url,
            store_id=settings.iris_store_id,
            api_key=settings.iris_api_key,
        )
        self.am.health()  # fail fast if unreachable

    # --- (de)serialization to a single LTM record -------------------------
    def _encode(self, it: ContextItem) -> dict:
        payload = it.to_dict()
        payload.pop("text", None)  # belief lives before the trailer, not in JSON
        text = it.text + _TRAILER + json.dumps(payload, ensure_ascii=False)
        return {
            "id": it.id,
            "text": text,
            "memory_type": "semantic",
            "owner_id": self.settings.owner_id,
            "namespace": self.settings.iris_namespace,
            "topics": [f"kind:{it.kind.value}", f"status:{it.status}",
                       f"v:{it.version}"],
        }

    @staticmethod
    def _decode(mem) -> ContextItem:
        text = getattr(mem, "text", "") or ""
        belief, _, trailer = text.partition(_TRAILER)
        d = json.loads(trailer) if trailer else {}
        d["text"] = belief
        d.setdefault("id", getattr(mem, "id", ""))
        return _to_item(d)

    def _filter(self, kind: ItemKind | None):
        """Build a LongTermMemoryFilter scoped to this owner+namespace (+kind)."""
        from redis_agent_memory import models  # noqa: PLC0415

        kwargs = dict(
            owner_id=models.OwnerIDFilter(eq=self.settings.owner_id),
            namespace=models.NamespaceFilter(eq=self.settings.iris_namespace),
        )
        if kind is not None:
            kwargs["topics"] = models.TopicsFilter(all=[f"kind:{kind.value}"])
        return models.LongTermMemoryFilter(**kwargs)

    def add(self, items: list[ContextItem]) -> int:
        from redis_agent_memory import models  # noqa: PLC0415

        if not items:
            return 0
        records = []
        for it in items[:100]:
            enc = self._encode(it)
            records.append(models.CreateMemoryRecord(
                id=enc["id"], text=enc["text"],
                memory_type=models.MemoryType.SEMANTIC,
                owner_id=enc["owner_id"], namespace=enc["namespace"],
                topics=enc["topics"],
            ))
        res = self.am.bulk_create_long_term_memories(memories=records)
        for e in (getattr(res, "errors", None) or []):
            log.warning("Iris LTM create failed id=%s: %s",
                        getattr(e, "id", "?"), getattr(e, "error", "?"))
        return len(getattr(res, "created", []) or [])

    def update(self, item: ContextItem) -> bool:
        enc = self._encode(item)
        self.am.update_long_term_memory(
            memory_id=item.id, text=enc["text"], topics=enc["topics"]
        )
        return True

    def _browse(self, kind: ItemKind | None = None) -> list[ContextItem]:
        from redis_agent_memory import models  # noqa: PLC0415

        res = self.am.search_long_term_memory(request=models.SearchLongTermMemoryRequestContent(
            filter_op=models.FilterConjunction.ALL, filter_=self._filter(kind), limit=100,
        ))
        return [self._decode(m) for m in res.items]

    def get(self, item_id: str) -> ContextItem | None:
        try:
            return self._decode(self.am.get_long_term_memory(memory_id=item_id))
        except Exception:  # noqa: BLE001 - not found / transient -> treat as absent
            return None

    def all(self, kind: ItemKind | None = None) -> list[ContextItem]:
        return self._browse(kind)

    def search(
        self, query_text: str, vector: list[float], top_k: int,
        kind: ItemKind | None = None,
    ) -> list[SearchHit]:
        from redis_agent_memory import models  # noqa: PLC0415

        res = self.am.search_long_term_memory(request=models.SearchLongTermMemoryRequestContent(
            text=query_text, similarity_threshold=0.0,
            filter_op=models.FilterConjunction.ALL, filter_=self._filter(kind),
            limit=max(top_k * 3, top_k),
        ))
        candidates = [self._decode(m) for m in res.items]
        # Iris ranks them; we re-score locally so hits carry a transparent cosine.
        return _rescore_local(query_text, candidates, top_k, self.settings)

    def clear(self) -> None:
        ids = [it.id for it in self._browse()]
        if ids:
            self.am.bulk_delete_long_term_memories(memory_ids=ids)


def _rescore_local(
    query_text: str, candidates: list[ContextItem], top_k: int, settings: Settings
) -> list[SearchHit]:
    """Re-rank Iris candidates with our own embedder so hits carry a real cosine.

    Iris exposes no per-item score; we keep scoring under our control (the same
    cosine the local/Redis stores use), which is what the revision layer needs.
    """
    import numpy as np

    from .embeddings import embed_batch

    if not candidates:
        return []
    vecs = embed_batch([query_text] + [c.embed_text() for c in candidates], settings)
    q = np.asarray(vecs[0], dtype=np.float32)
    qn = float(np.linalg.norm(q)) or 1.0
    q = q / qn
    scored = []
    for cand, cv in zip(candidates, vecs[1:]):
        v = np.asarray(cv, dtype=np.float32)
        vn = float(np.linalg.norm(v)) or 1.0
        scored.append(SearchHit(cand, float(q @ (v / vn))))
    scored.sort(key=lambda h: -h.score)
    return scored[:top_k]


def get_store(settings: Settings = SETTINGS):
    """Return the configured store, falling back to LocalStore if unavailable."""
    backend = settings.store_backend
    if backend == "iris":
        try:
            return IrisStore(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("Iris store unavailable (%s); using local store", exc)
    elif backend == "redis":
        try:
            return RedisStore(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis store unavailable (%s); using local store", exc)
    return LocalStore(settings)
