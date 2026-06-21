"""Paper ingestion: fetch -> embed -> bulk-load RedisVL (SPEC §6 Digest path).

Replaces the spec's local ``pubmed.py``: the *fetch* step is delegated to the
existing multi-source ``DataPipeline`` (implementations/data_pipeline), which
already does esearch/efetch plus arXiv/bioRxiv/Nature and cross-source dedupe.
This module only adds the embed + Redis bulk-load on top.

    from implementations.data_pipeline import DataPipeline
"""

from __future__ import annotations

from .config import SETTINGS, Settings
from .models import PaperOut


def fetch_recent(query: str, days: int, max_per_source: int = 50,
                 settings: Settings = SETTINGS) -> list[PaperOut]:
    """Pull recent papers across sources via ``DataPipeline`` and adapt each
    ``data_pipeline.Paper`` to ``PaperOut``."""
    raise NotImplementedError


def ingest(query: str, days: int, settings: Settings = SETTINGS) -> int:
    """Fetch -> embed abstracts -> upsert into the RedisVL index. Returns count."""
    raise NotImplementedError
