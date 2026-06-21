"""Phase 2 — embeddings deterministic fallback (no OpenAI key).

These run against the degraded path: correct dim, deterministic, normalized.
"""

from __future__ import annotations

import math

from app.config import Settings
from app.embeddings import embed_batch, embed_text

# Force the degraded path explicitly (no key) so tests never hit the network.
_SETTINGS = Settings(openai_api_key=None)


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def test_embed_text_dim_is_1536() -> None:
    vec = embed_text("gut microbiome butyrate", _SETTINGS)
    assert len(vec) == _SETTINGS.embed_dim == 1536


def test_embed_text_is_deterministic() -> None:
    a = embed_text("same input string", _SETTINGS)
    b = embed_text("same input string", _SETTINGS)
    assert a == b


def test_embed_text_distinct_inputs_differ() -> None:
    assert embed_text("alpha", _SETTINGS) != embed_text("beta", _SETTINGS)


def test_embed_text_is_normalized() -> None:
    vec = embed_text("normalize me", _SETTINGS)
    assert math.isclose(_norm(vec), 1.0, rel_tol=1e-9, abs_tol=1e-9)


def test_embed_batch_returns_n_vectors_each_1536() -> None:
    texts = ["one", "two", "three"]
    vecs = embed_batch(texts, _SETTINGS)
    assert len(vecs) == len(texts)
    for v in vecs:
        assert len(v) == 1536
        assert math.isclose(_norm(v), 1.0, rel_tol=1e-9, abs_tol=1e-9)


def test_embed_batch_matches_embed_text() -> None:
    [single] = embed_batch(["consistency"], _SETTINGS)
    assert single == embed_text("consistency", _SETTINGS)


def test_embed_batch_empty() -> None:
    assert embed_batch([], _SETTINGS) == []
