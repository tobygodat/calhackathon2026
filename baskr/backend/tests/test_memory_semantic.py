"""Phase 2 — memory.retrieve_relevant uses the semantic (embedding) path.

Uses fakeredis (like the Phase 1 unit tests) to seed a profile, and monkeypatches
the embedder with a tiny deterministic stub so the cosine ordering is a hard
assertion: an obviously-related item ranks above an unrelated one.
"""

from __future__ import annotations

import fakeredis
import pytest

from app import embeddings, memory, redis_client
from app.config import Settings
from app.models import ProfileItemKind


@pytest.fixture()
def settings() -> Settings:
    return Settings(redis_url="redis://fake", lab_id="semantic-test-lab")


@pytest.fixture(autouse=True)
def fake_client(monkeypatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(redis_client, "get_client", lambda settings=None: fake)
    monkeypatch.setattr(memory, "get_client", lambda settings=None: fake)
    return fake


# A tiny deterministic 3-dim "embedding" keyed on topical content. Vectors are
# constructed so the colitis/butyrate item is near the colitis query and the
# astronomy item is orthogonal — making the cosine ordering unambiguous.
def _stub_embed_text(text: str, settings=None) -> list[float]:
    t = text.lower()
    gut = 1.0 if any(w in t for w in ("butyrate", "colitis", "gut", "microbiome", "scfa")) else 0.0
    space = 1.0 if any(w in t for w in ("galaxy", "telescope", "star", "astronomy")) else 0.0
    other = 1.0 if not gut and not space else 0.0
    return [gut, space, other]


def _stub_embed_batch(texts, settings=None) -> list[list[float]]:
    return [_stub_embed_text(t, settings) for t in texts]


@pytest.fixture(autouse=True)
def stub_embedder(monkeypatch) -> None:
    monkeypatch.setattr(memory, "embed_text", _stub_embed_text, raising=False)
    monkeypatch.setattr(memory, "embed_batch", _stub_embed_batch, raising=False)
    # Also patch the source module in case memory imports lazily.
    monkeypatch.setattr(embeddings, "embed_text", _stub_embed_text)
    monkeypatch.setattr(embeddings, "embed_batch", _stub_embed_batch)


def _seed(settings) -> None:
    memory.append_item(ProfileItemKind.FINDING,
                       "Butyrate from gut microbiome SCFA reduces colitis inflammation",
                       settings)
    memory.append_item(ProfileItemKind.OPEN_QUESTION,
                       "How do distant galaxy clusters form, observed by telescope",
                       settings)


def test_returns_at_most_k(settings) -> None:
    _seed(settings)
    out = memory.retrieve_relevant("colitis and butyrate in the gut", k=1, settings=settings)
    assert len(out) <= 1


def test_related_item_ranks_above_unrelated(settings) -> None:
    _seed(settings)
    ranked = memory.retrieve_relevant("colitis and butyrate in the gut", k=2, settings=settings)
    assert len(ranked) == 2
    # The gut/colitis finding must come first via the embedding cosine path.
    assert "Butyrate" in ranked[0].text
    assert "galaxy" in ranked[1].text


def test_empty_profile_returns_empty(settings) -> None:
    out = memory.retrieve_relevant("anything", settings=settings)
    assert out == []
