"""Environment, model names, and thresholds for the Baskr backend (SPEC §11).

This is the one place that reads ``os.environ``. Everything else takes a
``Settings`` instance. Values mirror ``baskr/.env.example``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # --- secrets / connections ---
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # Surfaced for completeness (SPEC §11). Paper fetching is delegated to
    # implementations/data_pipeline, which reads NCBI_API_KEY from its own Config.
    ncbi_api_key: str | None = os.environ.get("NCBI_API_KEY")

    # --- lab / behavior ---
    lab_id: str = os.environ.get("BASKR_LAB_ID", "gut-microbiome-demo")
    relevance_threshold: float = float(os.environ.get("BASKR_RELEVANCE_THRESHOLD", "0.5"))

    # --- models ---
    embed_model: str = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    embed_dim: int = 1536  # text-embedding-3-small
    # Default confirmed at build time (SPEC §4); overridable via REASON_MODEL.
    reason_model: str = os.environ.get("REASON_MODEL") or "claude-sonnet-4-6"

    # --- retrieval / engine knobs ---
    memory_top_k: int = 8          # profile items pulled per classification (SPEC §6)
    active_search_cap: int = 5     # max hits returned by /api/search (SPEC §6)
    active_search_days: int = 7    # PubMed lookback window for active search

    # --- redis key map (SPEC §5.5) ---
    paper_key_prefix: str = "baskr:paper:"
    papers_index: str = "baskr:idx:papers"
    digest_key_prefix: str = "baskr:digest:"


SETTINGS = Settings()
