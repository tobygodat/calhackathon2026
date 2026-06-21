# do not include in test1
"""Seed both context profiles into BOTH stores (SPEC §5.1).

For each profile JSON under ``data/``:
  - local Redis  (``lab:{lab_id}:profile`` + ``lab:{lab_id}:items``) — powers
    ``/api/profile`` display and the local-memory fallback.
  - Iris Agent Memory (LTM, namespace ``lab-{lab_id}``) — powers the engine's
    semantic recall (memory.retrieve_relevant) when Iris is configured.

Item ids are preserved verbatim in both stores so a paper's matched_item_id lines
up with what the profile panel shows. Re-running is idempotent (local namespace is
cleared first; Iris uses deterministic record ids).

Run:  python scripts/seed_profiles.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

# Make the baskr/backend package (app.*) importable.
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app import agent_memory  # noqa: E402
from app.config import SETTINGS  # noqa: E402
from app.models import Profile  # noqa: E402
from app.redis_client import get_client  # noqa: E402

_DATA = Path(__file__).resolve().parents[1] / "data"

# (json file, lab_id). The first is the active default (BASKR_LAB_ID).
PROFILES = [
    ("profile_seed.json", "gut-microbiome-demo"),
    ("profile_seed_blueprint.json", "blueprint-self-tracker"),
]


def _load(path: str) -> Profile:
    return Profile(**json.loads((_DATA / path).read_text(encoding="utf-8")))


def _seed_local(profile: Profile, settings) -> int:
    """Clear and rewrite the lab's local-Redis namespace; ids preserved."""
    client = get_client(settings)
    ns = f"lab:{settings.lab_id}"
    for key in client.scan_iter(f"{ns}:*"):
        client.delete(key)
    client.hset(f"{ns}:profile", mapping={
        "lab_id": profile.lab_id,
        "niche": profile.niche,
        "display_name": profile.display_name,
    })
    if profile.items:
        client.hset(f"{ns}:items",
                    mapping={it.id: it.model_dump_json() for it in profile.items})
    return len(profile.items)


def main() -> None:
    iris_on = agent_memory.is_enabled()
    print(f"Iris Agent Memory enabled: {iris_on}")
    for path, lab_id in PROFILES:
        settings = dataclasses.replace(SETTINGS, lab_id=lab_id)
        profile = _load(path)
        n_local = _seed_local(profile, settings)
        n_iris = 0
        if iris_on:
            n_iris = agent_memory.seed_profile_items(
                lab_id,
                [{"id": it.id, "kind": it.kind.value, "text": it.text}
                 for it in profile.items],
            )
        print(f"  {lab_id:24s} local={n_local} iris={n_iris}  ({profile.display_name})")


if __name__ == "__main__":
    main()
