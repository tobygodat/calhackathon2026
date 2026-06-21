# do not include in test1
"""Iris Redis Agent Memory — managed long-term memory (LTM) for the lab profile.

The lab/personal context profile IS the agent's long-term memory: one LTM record
per profile item, namespaced per lab. The engine recalls the top-k semantically
nearest items for a paper via ``search_long_term_memory`` (see memory.py), and
Active Search questions are recorded as **session events** so the managed
promotion worker grows long-term memory over time (SPEC §5.1, §6 write-back).

Config (from baskr/.env, loaded by app.config._load_dotenv):
    AGENT_MEMORY_BASE_URL · AGENT_MEMORY_STORE_ID · AGENT_MEMORY_API_KEY

When those are unset (or in tests), ``is_enabled()`` is False and callers fall
back to the local Redis-native memory (memory.py), so the app still runs offline.

This module stays decoupled from the domain models: it speaks dicts
(``{"id", "kind", "text", "score"}``) and lets memory.py build ``ProfileItem``s.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("baskr.agent_memory")

_ENV_KEYS = ("AGENT_MEMORY_BASE_URL", "AGENT_MEMORY_STORE_ID", "AGENT_MEMORY_API_KEY")

# LTM record ids must be [a-zA-Z0-9-], 1–64 chars.
_ID_UNSAFE = re.compile(r"[^a-zA-Z0-9-]")

_client: Any = None


def is_enabled() -> bool:
    """True when all Iris credentials are configured (else use local fallback).

    Single chokepoint so tests can force the local path (see tests/conftest.py)."""
    return all(os.environ.get(k) for k in _ENV_KEYS)


def get_client() -> Any:
    """Return a cached ``AgentMemory`` client built from the environment."""
    global _client
    if _client is None:
        from redis_agent_memory import AgentMemory  # noqa: PLC0415
        _client = AgentMemory(
            os.environ["AGENT_MEMORY_BASE_URL"],
            store_id=os.environ["AGENT_MEMORY_STORE_ID"],
            api_key=os.environ["AGENT_MEMORY_API_KEY"],
        )
    return _client


def reset_client() -> None:
    """Drop the cached client (tests / credential rotation)."""
    global _client
    _client = None


# --- key helpers -----------------------------------------------------------

def namespace(lab_id: str) -> str:
    """LTM namespace for a lab. Iris namespaces allow only ``[A-Za-z0-9-]`` (no
    colon), so this mirrors the local ``lab:{id}`` root as ``lab-{id}``."""
    return _ID_UNSAFE.sub("-", f"lab-{lab_id}")


def _record_id(lab_id: str, item_id: str) -> str:
    """Deterministic, charset-safe LTM id so re-seeding never duplicates."""
    return _ID_UNSAFE.sub("-", f"{lab_id}-{item_id}")[:64]


# Topics carry the structured fields LTM records don't have first-class slots for,
# so recall can reconstruct the original ProfileItem (id + kind) exactly.
def _topics(kind: str, item_id: str) -> list[str]:
    return ["profile", f"kind:{kind}", f"item:{item_id}"]


def _parse_topics(topics: list[str] | None) -> tuple[str, str | None]:
    """Recover (kind, item_id) from a record's topics (best-effort)."""
    kind, item_id = "finding", None
    for t in topics or []:
        if t.startswith("kind:"):
            kind = t[len("kind:"):]
        elif t.startswith("item:"):
            item_id = t[len("item:"):]
    return kind, item_id


# --- writes ----------------------------------------------------------------

def seed_profile_items(lab_id: str, items: list[dict], settings: Any = None) -> int:
    """Bulk-create one LTM record per profile item; returns the count created.

    ``items`` are dicts with ``id``/``kind``/``text``. Deterministic ids make this
    idempotent — re-seeding overwrites the same records instead of duplicating."""
    from redis_agent_memory import models  # noqa: PLC0415

    if not items:
        return 0
    records = [
        {
            "id": _record_id(lab_id, it["id"]),
            "text": it["text"],
            "memory_type": models.MemoryType.SEMANTIC,
            "namespace": namespace(lab_id),
            "owner_id": lab_id,
            "topics": _topics(it["kind"], it["id"]),
        }
        for it in items
    ]
    res = get_client().bulk_create_long_term_memories(memories=records[:100])
    if getattr(res, "errors", None):
        for err in res.errors:
            log.warning("LTM seed failed id=%s reason=%s", err.id, err.error)
    return len(getattr(res, "created", []) or [])


def add_memory(lab_id: str, text: str, kind: str = "finding",
               item_id: str | None = None) -> str | None:
    """Append a single LTM record (the stretch 'memory grows' write-back)."""
    from redis_agent_memory import models  # noqa: PLC0415

    item_id = item_id or f"{kind[:3]}-{int(datetime.now(timezone.utc).timestamp())}"
    rec = {
        "id": _record_id(lab_id, item_id),
        "text": text,
        "memory_type": models.MemoryType.SEMANTIC,
        "namespace": namespace(lab_id),
        "owner_id": lab_id,
        "topics": _topics(kind, item_id),
    }
    res = get_client().bulk_create_long_term_memories(memories=[rec])
    created = getattr(res, "created", []) or []
    return created[0] if created else None


def record_search_event(lab_id: str, question: str) -> str | None:
    """Record an Active Search question as a session event so the managed
    promotion worker can extract durable facts into LTM over time."""
    from redis_agent_memory import models  # noqa: PLC0415

    res = get_client().add_session_event(
        actor_id=lab_id,
        role=models.MessageRole.USER,
        content=[{"text": question}],
        created_at=datetime.now(timezone.utc),
    )
    return getattr(getattr(res, "event", None), "event_id", None)


# --- reads -----------------------------------------------------------------

def recall(query: str, lab_id: str, k: int = 8,
           similarity_threshold: float = 0.0) -> list[dict]:
    """Semantic top-k recall of profile items for a paper/query, namespaced.

    Returns dicts ``{"id", "kind", "text", "score"}`` ordered by similarity. A low
    default threshold favours recall (the profile is small; we want the engine to
    always see the most-relevant items rather than an empty page)."""
    from redis_agent_memory import models  # noqa: PLC0415

    res = get_client().search_long_term_memory(request={
        "text": query,
        "similarity_threshold": similarity_threshold,
        "filter_op": models.FilterConjunction.ALL,
        "filter_": {"namespace": {"eq": namespace(lab_id)}},
        "limit": k,
    })
    out: list[dict] = []
    for m in res.items:  # results are ordered by similarity; no per-item score field
        kind, item_id = _parse_topics(getattr(m, "topics", None))
        out.append({
            "id": item_id or getattr(m, "id", ""),
            "kind": kind,
            "text": getattr(m, "text", ""),
            "score": getattr(m, "score", None),
        })
    return out


def count(lab_id: str) -> int:
    """Number of LTM records in a lab's namespace (capped at 100, for /status).

    Uses no-query browsing — structured filter only, no vector ranking."""
    res = get_client().search_long_term_memory(request={
        "filter_": {"namespace": {"eq": namespace(lab_id)}},
        "limit": 100,
    })
    return len(res.items)


def health() -> Any:
    """Iris service health (for /status)."""
    return get_client().health()
