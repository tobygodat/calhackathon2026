"""Lab context profile storage.

Loads profile from data/profile_seed.json. In-memory retrieval (no Redis
Agent Memory required for the demo path). Append writes back to the JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import SETTINGS, Settings
from .models import Profile, ProfileItem, ProfileItemKind
from .seed_profile import SEED_PATH, load_seed

# Module-level cache so we only read the file once per process.
_profile_cache: Profile | None = None


def load_profile(settings: Settings = SETTINGS) -> Profile:
    """Return the lab profile, loading from JSON on first call."""
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = load_seed()
    return _profile_cache


def retrieve_relevant(query: str, k: int = SETTINGS.memory_top_k,
                      settings: Settings = SETTINGS) -> list[ProfileItem]:
    """Return up to k profile items. No vector search — returns all items for the demo."""
    profile = load_profile(settings)
    return profile.items[:k]


def append_item(kind: ProfileItemKind, text: str,
                settings: Settings = SETTINGS) -> Profile:
    """Append a new profile item and persist to JSON."""
    global _profile_cache
    profile = load_profile(settings)
    new_id = f"{kind.value[:3]}_{len(profile.items) + 1}"
    new_item = ProfileItem(id=new_id, kind=kind, text=text)
    updated_items = list(profile.items) + [new_item]
    updated = Profile(
        lab_id=profile.lab_id,
        niche=profile.niche,
        display_name=profile.display_name,
        items=updated_items,
    )
    # Persist to JSON
    data = {
        "lab_id": updated.lab_id,
        "niche": updated.niche,
        "display_name": updated.display_name,
        "items": [
            {"id": it.id, "kind": it.kind.value, "text": it.text}
            for it in updated.items
        ],
    }
    SEED_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _profile_cache = updated
    return updated
