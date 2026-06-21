"""Seed Agent Memory from ``data/profile_seed.json`` (SPEC §5.1, §3).

Reads the profile seed file and returns a Profile object.
Run as a one-off:  python -m app.seed_profile
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import SETTINGS, Settings
from .models import Profile

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "profile_seed.json"


def load_seed(path: Path = SEED_PATH) -> Profile:
    """Parse the seed JSON into a ``Profile``."""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return Profile(**data)


def seed(settings: Settings = SETTINGS) -> int:
    """Load seed profile. Returns number of items loaded."""
    profile = load_seed()
    return len(profile.items)


if __name__ == "__main__":
    profile = load_seed()
    print(f"Loaded profile: {profile.display_name}")
    print(f"Items: {len(profile.items)}")
    for item in profile.items:
        print(f"  [{item.kind}] {item.id}: {item.text[:60]}...")
