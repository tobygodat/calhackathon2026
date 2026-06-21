"""Seed Agent Memory from ``data/profile_seed.json`` (SPEC §5.1, §3).

Reads the profile seed file (placeholder content for now; swap for the real
gut-microbiome lab profile before the demo) and writes one memory per item into
the ``lab:{lab_id}`` namespace via ``memory.append_item``.

Idempotency
-----------
``seed()`` CLEARS the lab namespace (items + per-prefix id counters + profile
metadata) before re-writing, then appends every seed item fresh. Re-running is
therefore safe and convergent: the namespace always ends with exactly the seed
items and never accumulates duplicates or drifts on item ids. The profile-level
metadata (lab_id / niche / display_name) is written from the seed file so the
seeded profile matches it verbatim.

Run as a one-off:  python -m app.seed_profile
"""

from __future__ import annotations

import json
from pathlib import Path

from . import memory
from .config import SETTINGS, Settings
from .models import Profile
from .redis_client import get_client

# data/profile_seed.json relative to the baskr/ repo root.
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "profile_seed.json"


def load_seed(path: Path = SEED_PATH) -> Profile:
    """Parse the seed JSON into a ``Profile``."""
    payload = json.loads(Path(path).read_text())
    return Profile(**payload)


def _clear_namespace(profile: Profile, settings: Settings) -> None:
    """Delete all lab-namespace keys so re-seeding is idempotent."""
    client = get_client(settings)
    pattern = f"lab:{settings.lab_id}:*"
    keys = list(client.keys(pattern))
    if keys:
        client.delete(*keys)

    # Write profile-level metadata from the seed file (matches §5.1 verbatim).
    client.hset(
        f"lab:{settings.lab_id}:profile",
        mapping={
            "lab_id": profile.lab_id,
            "niche": profile.niche,
            "display_name": profile.display_name,
        },
    )


def seed(settings: Settings = SETTINGS) -> int:
    """Write every seed item into Agent Memory. Returns number of items written."""
    profile = load_seed()
    _clear_namespace(profile, settings)

    for item in profile.items:
        memory.append_item(item.kind, item.text, settings)

    return len(profile.items)


if __name__ == "__main__":
    count = seed()
    print(f"Seeded {count} profile items into lab:{SETTINGS.lab_id}")
