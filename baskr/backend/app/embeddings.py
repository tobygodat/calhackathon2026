"""OpenAI ``text-embedding-3-small`` wrapper (SPEC §5.2, §6).

Embeds the full abstract (~250 words; no chunking by default). Returns 1536-dim
vectors. Scaffold only.
"""

from __future__ import annotations

from .config import SETTINGS, Settings


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string with ``settings.embed_model``."""
    raise NotImplementedError


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings in one call (used by ingest bulk-load)."""
    raise NotImplementedError
