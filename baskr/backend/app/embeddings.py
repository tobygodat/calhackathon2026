# do not include in test1
"""Text embeddings for the RedisVL papers index (SPEC §5.2, §6).

Two backends, selected at call time by whether an OpenAI key is configured:

- **OpenAI** ``text-embedding-3-small`` (1536-dim) when ``settings.openai_api_key``
  is set — real semantic vectors for meaningful nearest-neighbour search.
- **Local keyless** hashed bag-of-tokens projection otherwise — deterministic,
  dependency-light (numpy only), no network. Used in the degraded/offline path
  and throughout the test suite.

Both produce ``settings.embed_dim`` (1536) vectors matching the index, so the two
are interchangeable at rest. Anthropic offers no embeddings endpoint, so the
classification *reasoning* still runs entirely through Claude (app/llm.py); these
vectors exist only to populate and query the papers index.
"""

from __future__ import annotations

import hashlib
import logging

from .config import SETTINGS, Settings

log = logging.getLogger("baskr.embeddings")


def _should_use_openai(settings: Settings) -> bool:
    """True when a real OpenAI embedding call should be made for ``settings``.

    Single chokepoint so the test suite can force the keyless path even though
    ``.env`` now provides an ``OPENAI_API_KEY`` (see tests/conftest.py)."""
    return bool(getattr(settings, "openai_api_key", None))


def _embed_one(text: str, dim: int) -> list[float]:
    """Hash tokens into a fixed-width vector, then L2-normalize (no API/key)."""
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


def _embed_openai(texts: list[str], settings: Settings) -> list[list[float]]:
    """Embed ``texts`` with OpenAI ``settings.embed_model`` in one batched call."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.embeddings.create(model=settings.embed_model, input=texts)
    # The API may return items out of order; sort by index to match the input.
    return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string into a ``settings.embed_dim`` vector."""
    return embed_batch([text], settings)[0]


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings (used by the ingest bulk-load). Preserves input order.

    Uses OpenAI when a key is configured; on any OpenAI failure (or no key) it
    falls back to the local keyless embedder so ingest/search never hard-fail."""
    if not texts:
        return []
    if _should_use_openai(settings):
        try:
            return _embed_openai(texts, settings)
        except Exception as exc:  # noqa: BLE001 — degrade to keyless, never hard-fail
            log.warning("OpenAI embeddings failed (%s); using keyless fallback", exc)
    return [_embed_one(t, settings.embed_dim) for t in texts]
