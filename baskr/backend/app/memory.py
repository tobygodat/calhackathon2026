"""Redis Agent Memory read/write for the lab context profile (SPEC §5.1, §5.5).

The profile lives in the ``lab:{lab_id}`` Agent Memory namespace, one memory per
item. ``retrieve_relevant`` does the semantic top-k pull the engine uses (k≈8);
``append_item`` backs the stretch memory write-back so memory visibly grows.

Backing store (Phase 1 decision)
---------------------------------
No managed Redis Agent Memory server exists in this environment, so the profile is
stored **directly in Redis** behind these same signatures, keeping the engine
decoupled from the backing store:

- ``lab:{lab_id}:profile``      Hash  -> profile-level fields (lab_id, niche, display_name)
- ``lab:{lab_id}:items``        Hash  -> {item_id: json(ProfileItem)} (one field per item)
- ``lab:{lab_id}:item_seq``     int   -> monotonic id counter per kind-prefix

``retrieve_relevant`` ranks with a deterministic **lexical token-overlap** scorer
(Jaccard-style). This is intentionally a placeholder ranker so the function is real
and testable now with NO embeddings; Phase 2+ swaps it for semantic KNN over
embedded items while keeping this signature.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .config import SETTINGS, Settings
from .models import Profile, ProfileItem, ProfileItemKind
from .redis_client import get_client

# Default profile-level metadata when the namespace has not been seeded yet.
_DEFAULT_NICHE = "gut_microbiome"
_DEFAULT_DISPLAY_NAME = "Demo Lab"

# Short id prefixes per kind (matches the SPEC §5.1 seed ids: oq_1, asm_1, fnd_1).
_KIND_PREFIX = {
    ProfileItemKind.OPEN_QUESTION: "oq",
    ProfileItemKind.ASSUMPTION: "asm",
    ProfileItemKind.FINDING: "fnd",
    ProfileItemKind.PLANNED_EXPERIMENT: "exp",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _ns(settings: Settings) -> str:
    """Agent Memory namespace root for this lab."""
    return f"lab:{settings.lab_id}"


def _profile_key(settings: Settings) -> str:
    return f"{_ns(settings)}:profile"


def _items_key(settings: Settings) -> str:
    return f"{_ns(settings)}:items"


def _seq_key(settings: Settings, prefix: str) -> str:
    return f"{_ns(settings)}:item_seq:{prefix}"


def _decode(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else value


def load_profile(settings: Settings = SETTINGS) -> Profile:
    """Read the full lab profile from Agent Memory (all items)."""
    client = get_client(settings)

    meta_raw = client.hgetall(_profile_key(settings)) or {}
    meta = {_decode(k): _decode(v) for k, v in meta_raw.items()}

    items_raw = client.hgetall(_items_key(settings)) or {}
    items: list[ProfileItem] = []
    for value in items_raw.values():
        payload = json.loads(_decode(value))
        items.append(ProfileItem(**payload))

    # Stable, human-friendly order: by kind, then id.
    items.sort(key=lambda it: (it.kind.value, it.id))

    return Profile(
        lab_id=meta.get("lab_id", settings.lab_id),
        niche=meta.get("niche", _DEFAULT_NICHE),
        display_name=meta.get("display_name", _DEFAULT_DISPLAY_NAME),
        items=items,
    )


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _overlap_score(query_tokens: set[str], item: ProfileItem) -> float:
    """Deterministic lexical relevance: Jaccard overlap of token sets.

    PLACEHOLDER ranker (Phase 1) — swapped for semantic KNN once embeddings land.
    """
    item_tokens = _tokenize(item.text)
    if not query_tokens or not item_tokens:
        return 0.0
    intersection = len(query_tokens & item_tokens)
    union = len(query_tokens | item_tokens)
    return intersection / union if union else 0.0


def retrieve_relevant(query: str, k: int = SETTINGS.memory_top_k,
                      settings: Settings = SETTINGS) -> list[ProfileItem]:
    """Top-k retrieval of profile items for a paper/query (SPEC §6).

    Uses a deterministic lexical token-overlap ranker (placeholder until semantic
    embeddings land in a later phase). Ties break on item id for stability.
    """
    items = load_profile(settings).items
    query_tokens = _tokenize(query)
    ranked = sorted(
        items,
        key=lambda it: (_overlap_score(query_tokens, it), it.id),
        reverse=True,
    )
    return ranked[:k]


def append_item(kind: ProfileItemKind, text: str,
                settings: Settings = SETTINGS) -> Profile:
    """Append a new profile item (stretch write-back); return updated profile.

    Assigns a stable id of the form ``{prefix}_{n}`` (e.g. ``fnd_4``) using a
    per-prefix Redis counter so ids never collide with the seed set.
    """
    client = get_client(settings)
    prefix = _KIND_PREFIX[kind]
    seq = client.incr(_seq_key(settings, prefix))
    item_id = f"{prefix}_{seq}"

    item = ProfileItem(id=item_id, kind=kind, text=text)
    client.hset(_items_key(settings), item_id, item.model_dump_json())

    # Ensure profile-level metadata exists so a fresh namespace still reports sanely.
    client.hsetnx(_profile_key(settings), "lab_id", settings.lab_id)
    client.hsetnx(_profile_key(settings), "niche", _DEFAULT_NICHE)
    client.hsetnx(_profile_key(settings), "display_name", _DEFAULT_DISPLAY_NAME)

    return load_profile(settings)


def profile_item_count(settings: Settings = SETTINGS) -> int:
    """Number of stored profile items (for /status memory_records). Never raises here."""
    return int(get_client(settings).hlen(_items_key(settings)))
