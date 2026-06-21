# do not include in test1
"""Environment, model names, and thresholds for the Baskr backend (SPEC §11).

This is the one place that reads ``os.environ``. Everything else takes a
``Settings`` instance. Values mirror ``baskr/.env.example``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load baskr/.env into os.environ (real env always wins)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value

    # If REDIS_URL looks like a redis-cli command or local placeholder,
    # reconstruct from REDIS_PUBLIC_ENDPOINT + REDIS_PASSWORD if available.
    raw_url = os.environ.get("REDIS_URL", "")
    endpoint = os.environ.get("REDIS_PUBLIC_ENDPOINT", "")
    password = os.environ.get("REDIS_PASSWORD", "")
    if endpoint and password:
        # Always prefer the explicit endpoint + password over a pasted cli string
        proper_url = f"redis://default:{password}@{endpoint}"
        os.environ["REDIS_URL"] = proper_url


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # --- secrets / connections ---
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    # OpenAI key enables real text-embedding-3-small vectors for RedisVL search.
    # When None, app/embeddings.py falls back to the local keyless hash embedder.
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
    # Surfaced for completeness (SPEC §11). Paper fetching is delegated to
    # implementations/data_pipeline, which reads NCBI_API_KEY from its own Config.
    ncbi_api_key: str | None = os.environ.get("NCBI_API_KEY")

    # --- lab / behavior ---
    lab_id: str = os.environ.get("BASKR_LAB_ID", "gut-microbiome-demo")
    relevance_threshold: float = float(os.environ.get("BASKR_RELEVANCE_THRESHOLD", "0.5"))

    # --- models ---
    # Embeddings: real OpenAI text-embedding-3-small when openai_api_key is set,
    # else the local keyless hash embedder (app/embeddings.py). Both are 1536-dim,
    # matching the RedisVL papers index, so the two are interchangeable at rest.
    embed_model: str = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    embed_dim: int = 1536
    # Reasoning model for the real Anthropic path (app/llm.py). Defaults to the
    # value documented in .env.example so classification works out of the box when
    # an API key is present but REASON_MODEL is unset.
    reason_model: str | None = os.environ.get("REASON_MODEL", "claude-sonnet-4-6")

    # --- retrieval / engine knobs ---
    memory_top_k: int = 8          # profile items pulled per classification (SPEC §6)
    active_search_cap: int = 5     # max hits returned by /api/search (SPEC §6)
    active_search_days: int = 7    # PubMed lookback window for active search

    # Opt-in agent-loop step 3 ("search prior work"): when true, classify_paper
    # embeds the paper and queries the Redis vector index for the top-N similar
    # prior papers, feeding them into the prompt. OFF by default so the default
    # classification path is unchanged and needs no Redis vector round-trip.
    use_vector_priorwork: bool = (
        os.environ.get("BASKR_USE_VECTOR_PRIORWORK", "").strip().lower()
        in ("1", "true", "yes", "on")
    )
    vector_priorwork_k: int = int(os.environ.get("BASKR_VECTOR_PRIORWORK_K", "5"))

    # --- classification throughput knobs ---
    # Bounded concurrency for classify_paper fan-out (engine.run_digest / active_search).
    classify_concurrency: int = int(os.environ.get("BASKR_CLASSIFY_CONCURRENCY", "5"))
    # Cheap pre-filter ceiling: active_search LLM-classifies at most this many of the
    # fetched papers (ranked by a keyless vector/lexical signal first), capping cost to
    # output size instead of fetch size.
    preclassify_cap: int = int(os.environ.get("BASKR_PRECLASSIFY_CAP", "20"))

    # --- redis key map (SPEC §5.5) ---
    paper_key_prefix: str = "baskr:paper:"
    papers_index: str = "baskr:idx:papers"
    digest_key_prefix: str = "baskr:digest:"


SETTINGS = Settings()
