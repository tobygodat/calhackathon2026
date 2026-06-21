"""OpenAI ``text-embedding-3-small`` wrapper (SPEC §5.2, §6).

Embeds the full abstract (~250 words; no chunking by default). Returns 1536-dim
vectors.
"""

from __future__ import annotations

from .config import SETTINGS, Settings


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string with ``settings.embed_model``."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=settings.embed_model, input=text)
    return response.data[0].embedding


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings in one call (used by ingest bulk-load)."""
    if not texts:
        return []
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=settings.embed_model, input=texts)
    # Preserve input order (OpenAI preserves order but index field is available)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
