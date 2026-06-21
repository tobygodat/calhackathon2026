"""OpenAI ``text-embedding-3-small`` wrapper (SPEC §5.2, §6).

Embeds the full abstract (~250 words; no chunking by default). Returns 1536-dim
L2-normalized vectors.

Two paths, same signatures:

- **Real:** when ``settings.openai_api_key`` is set, calls the OpenAI embeddings
  API with ``settings.embed_model``. ``embed_batch`` sends all texts in one request.
- **Degraded (no key):** a deterministic, hashed pseudo-embedding of dim
  ``settings.embed_dim`` (1536), L2-normalized and stable for the same input. This
  keeps the engine fully testable/demoable with NO API key while preserving the
  contract (correct dim, unit norm, deterministic). Clearly a stand-in — it carries
  no real semantics beyond stable per-text identity.
"""

from __future__ import annotations

import hashlib
import math
import struct

from .config import SETTINGS, Settings


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _deterministic_embedding(text: str, dim: int) -> list[float]:
    """Stable hashed pseudo-embedding of length ``dim``, L2-normalized.

    DEGRADED stand-in (no OpenAI key). Uses a SHA-256-seeded byte stream expanded
    to ``dim`` float32 values mapped into ``[-1, 1)``. Deterministic for a given
    input; different inputs almost surely produce different vectors.
    """
    out: list[float] = []
    counter = 0
    seed = text.encode("utf-8")
    while len(out) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()  # 32 bytes
        # 8 float32 values per 32-byte block.
        for i in range(0, len(block), 4):
            (raw,) = struct.unpack(">I", block[i : i + 4])
            out.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(out) >= dim:
                break
        counter += 1
    return _l2_normalize(out)


def _openai_client(settings: Settings):
    """Lazily build an OpenAI client (kept out of import path / degraded-safe)."""
    from openai import OpenAI  # noqa: PLC0415

    return OpenAI(api_key=settings.openai_api_key)


def embed_text(text: str, settings: Settings = SETTINGS) -> list[float]:
    """Embed a single string with ``settings.embed_model``.

    Real OpenAI call when a key is present; deterministic 1536-dim fallback
    otherwise. Always returns a vector of length ``settings.embed_dim``.
    """
    return embed_batch([text], settings)[0]


def embed_batch(texts: list[str], settings: Settings = SETTINGS) -> list[list[float]]:
    """Embed many strings in one call (used by ingest bulk-load).

    Returns one vector per input, each of length ``settings.embed_dim``. Real path
    batches all texts into a single OpenAI request.
    """
    if not texts:
        return []

    if settings.openai_api_key:
        client = _openai_client(settings)
        resp = client.embeddings.create(model=settings.embed_model, input=texts)
        # OpenAI preserves input order in ``data``; sort defensively by ``index``.
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]

    return [_deterministic_embedding(t, settings.embed_dim) for t in texts]
