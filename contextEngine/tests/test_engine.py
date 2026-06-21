"""End-to-end tests over the keyless/local path (no API keys, no infra)."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context_engine.config import SETTINGS
from context_engine.engine import ContextEngine
from context_engine.extractor import extract_items
from context_engine.models import ItemKind
from context_engine.pdf import chunk_text

SAMPLE = (
    "We find that dietary fiber increases short-chain fatty acid production in "
    "the colon. We assume that the gut microbiota composition is stable over the "
    "study period. It remains unknown whether these effects persist beyond twelve "
    "weeks, and future work should investigate longer time horizons. Our results "
    "show a clear dose-response relationship across all cohorts."
)


@pytest.fixture
def settings(tmp_path):
    # Force keyless extraction + local store into an isolated temp dir.
    return replace(SETTINGS, anthropic_api_key=None, openai_api_key=None,
                   store_backend="local", store_path=str(tmp_path / "store"))


def test_heuristic_extracts_all_three_kinds(settings):
    items = extract_items(SAMPLE, source_id="s1", source_title="t1", settings=settings)
    kinds = {it.kind for it in items}
    assert ItemKind.FINDING in kinds
    assert ItemKind.QUESTION in kinds
    assert ItemKind.ASSUMPTION in kinds


def test_chunking_covers_long_text(settings):
    long_text = SAMPLE * 200
    chunks = chunk_text(long_text, settings)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) >= len(long_text) * 0.9


def test_ingest_and_search_roundtrip(settings):
    eng = ContextEngine(settings)

    # Drive ingest directly off extracted items (skips PDF parsing).
    items = extract_items(SAMPLE, source_id="s1", source_title="paper", settings=settings)
    from context_engine.embeddings import embed_batch
    for it, v in zip(items, embed_batch([i.embed_text() for i in items], settings)):
        it.embedding = v
    assert eng.store.add(items) == len(items)

    hits = eng.search("short chain fatty acids from fiber", top_k=3)
    assert hits
    assert hits[0].score > 0  # keyless cosine still ranks something on top

    only_q = eng.search("future experiments", kind=ItemKind.QUESTION)
    assert all(h.item.kind == ItemKind.QUESTION for h in only_q)


def test_idempotent_add(settings):
    eng = ContextEngine(settings)
    items = extract_items(SAMPLE, source_id="s1", source_title="p", settings=settings)
    from context_engine.embeddings import embed_batch
    for it, v in zip(items, embed_batch([i.embed_text() for i in items], settings)):
        it.embedding = v
    n1 = eng.store.add(items)
    n2 = eng.store.add(items)  # same ids -> no duplicates
    assert n1 == len(items)
    assert n2 == 0
