"""Local, keyless text embeddings (SPEC §5.2, §6).

Embeds the full abstract (~250 words; no chunking by default) into a
``settings.embed_dim``-dimensional unit vector. The embedding is computed
locally with no external API call and no API key — a hashed bag-of-tokens
projection that is deterministic and dependency-light (numpy only).

Note: Anthropic does not offer an embeddings endpoint, so the classification
path runs entirely through Claude (see app/llm.py). These vectors exist only to
populate the optional RedisVL papers index; swap in a dedicated embedding
provider here if you need true semantic similarity.
"""

from __future__ import annotations

import hashlib

from .config import SETTINGS, Settings


def _embed_one(text: str, dim: int) -> list[float]:
    """Hash tokens into a fixed-width vector, then L2-normalize."""
    import numpy as np

    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        # Stable per-token bucket + sign from a content hash (no randomness).
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[bucket] += sign

    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec /= norm
    return vec.tolist()


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string into a ``settings.embed_dim`` vector."""
    return _embed_one(text, settings.embed_dim)


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings (used by ingest bulk-load). Preserves input order."""
    if not texts:
        return []
    return [_embed_one(t, settings.embed_dim) for t in texts]
