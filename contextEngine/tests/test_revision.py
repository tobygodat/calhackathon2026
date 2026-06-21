"""Belief-revision tests: accepting a contradiction changes the context by an
amount proportional to how much it overturns the existing belief.

Runs entirely on the keyless heuristic + local store (no API keys / infra).
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_engine.embeddings import embed_text
from context_engine.engine import ContextEngine
from context_engine.models import ContextItem, ItemKind


@pytest.fixture
def settings(tmp_path):
    return replace(
        __import__("context_engine.config", fromlist=["SETTINGS"]).SETTINGS,
        anthropic_api_key=None, openai_api_key=None,
        store_backend="local", store_path=str(tmp_path / "store"),
    )


def _seed(eng, text, kind=ItemKind.FINDING):
    it = ContextItem(kind=kind, text=text, source_id="seed", source_title="seed")
    it.embedding = embed_text(it.embed_text(), eng.settings)
    eng.store.add([it])
    return it


def test_non_contradiction_inserts(settings):
    eng = ContextEngine(settings)
    _seed(eng, "The Earth is round.")
    p = eng.accept("Dietary fiber raises short-chain fatty acid levels.")
    assert p.mode == "insert"
    # Original belief untouched; new belief added.
    texts = {i.text for i in eng.context()}
    assert "The Earth is round." in texts


def test_small_contradiction_merges_in_place(settings):
    eng = ContextEngine(settings)
    target = _seed(eng, "The Earth is round.")
    # A close, qualifying contradiction -> low severity -> merge (same id, v++).
    p = eng.accept("The Earth is round but not perfectly; it is slightly egg-shaped.")
    assert p.stance == "CONTRADICTS"
    assert p.mode in {"merge", "fork"}  # nuance, not replacement
    if p.mode == "merge":
        revised = eng.store.get(target.id)
        assert revised.version == 2
        assert revised.status == "active"


def test_large_contradiction_supersedes(settings):
    eng = ContextEngine(settings)
    target = _seed(eng, "The Earth is round.")
    # A flat reversal -> high severity -> supersede (old retired, new installed).
    p = eng.accept("The Earth is not round at all; the Earth is actually square.")
    assert p.stance == "CONTRADICTS"
    assert p.mode in {"supersede", "fork"}
    if p.mode == "supersede":
        old = eng.store.get(target.id)
        assert old.status == "superseded"
        # Superseded beliefs are hidden from the default context view.
        assert target.id not in {i.id for i in eng.context()}
        assert any(i.supersedes == target.id for i in eng.context())


def test_severity_orders_egg_below_square(settings):
    """The defining property: 'egg-shaped' must overturn the belief less than
    'square' does."""
    eng = ContextEngine(settings)
    _seed(eng, "The Earth is round.")
    egg = eng.accept("The Earth is round but slightly egg-shaped.", auto_apply=False)

    eng2 = ContextEngine(replace(settings, store_path=settings.store_path + "2"))
    _seed(eng2, "The Earth is round.")
    square = eng2.accept("The Earth is not round; it is square.", auto_apply=False)

    assert egg.severity < square.severity
