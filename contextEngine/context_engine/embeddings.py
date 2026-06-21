"""Text embeddings for the context-item vector store.

Two backends, chosen at call time by whether an OpenAI key is configured:

- **OpenAI** ``text-embedding-3-small`` (1536-dim) for real semantic vectors.
- **Local keyless** hashed bag-of-tokens projection otherwise — deterministic,
  numpy-only, no network. Used offline and throughout the tests.

Both emit ``settings.embed_dim`` (1536) L2-normalized vectors, so they are
interchangeable at rest and cosine similarity is just a dot product.
"""

from __future__ import annotations

import hashlib
import logging

from .config import SETTINGS, Settings

log = logging.getLogger("context_engine.embeddings")


def _embed_one_keyless(text: str, dim: int) -> list[float]:
    """Hash tokens into a fixed-width vector, then L2-normalize (no API/key)."""
    import numpy as np

    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[bucket] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec /= norm
    return vec.tolist()


def _embed_openai(texts: list[str], settings: Settings) -> list[list[float]]:
    """Embed ``texts`` with OpenAI in one batched call, input order preserved."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embed_model, input=texts)
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings, preserving order.

    Uses OpenAI when a key is set; on any failure (or no key) it falls back to the
    keyless embedder so ingest/search never hard-fail.
    """
    if not texts:
        return []
    if settings.openai_api_key:
        try:
            return _embed_openai(texts, settings)
        except Exception as exc:  # noqa: BLE001 - degrade, never hard-fail
            log.warning("OpenAI embeddings failed (%s); using keyless fallback", exc)
    return [_embed_one_keyless(t, settings.embed_dim) for t in texts]


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string into a ``settings.embed_dim`` vector."""
    return embed_batch([text], settings)[0]
