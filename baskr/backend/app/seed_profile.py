"""Seed Agent Memory from ``data/profile_seed.json`` (SPEC §5.1, §3).

Reads the profile seed file (placeholder content for now; swap for the real
gut-microbiome lab profile before the demo) and writes one memory per item into
the ``lab:{lab_id}`` namespace via ``memory.append_item``.

Run as a one-off:  python -m app.seed_profile
"""

from __future__ import annotations

from pathlib import Path

from .config import SETTINGS, Settings
from .models import Profile

# data/profile_seed.json relative to the baskr/ repo root.
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "profile_seed.json"


def load_seed(path: Path = SEED_PATH) -> Profile:
    """Parse the seed JSON into a ``Profile``."""
    raise NotImplementedError


def seed(settings: Settings = SETTINGS) -> int:
    """Write every seed item into Agent Memory. Returns number of items written."""
    raise NotImplementedError


if __name__ == "__main__":
    raise NotImplementedError
