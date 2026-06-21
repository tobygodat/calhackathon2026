"""Environment, model names, and store selection for the Context Engine.

This is the one place that reads ``os.environ``. Everything else takes a
``Settings`` instance. Mirrors the keyless-degrade philosophy of the baskr
backend: no keys / no infra still yields a runnable engine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load contextEngine/.env into os.environ (real env always wins)."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    # --- secrets ---
    # Claude extracts findings/questions/assumptions (extractor.py). When None, a
    # deterministic sentence-level heuristic stand-in is used instead.
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY") or None
    # OpenAI enables real text-embedding-3-small vectors; else keyless hashing.
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY") or None

    # --- models ---
    extract_model: str = os.environ.get("EXTRACT_MODEL", "claude-sonnet-4-6")
    embed_model: str = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    embed_dim: int = 1536  # matches text-embedding-3-small and the keyless embedder

    # --- vector store ---
    # "local" -> numpy file; "redis" -> RediSearch index; "iris" -> Redis Agent
    # Memory (durable, evolving belief store). All fall back to local if unavailable.
    store_backend: str = os.environ.get("CONTEXT_STORE", "local").strip().lower()
    store_path: str = os.environ.get("CONTEXT_STORE_PATH", "./.context_store")
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379")

    # The user this context belongs to (Iris owner_id / multi-tenant scoping).
    owner_id: str = os.environ.get("CONTEXT_OWNER_ID", "default-user")

    # --- Iris Redis Agent Memory (belief tier) ---
    iris_base_url: str | None = os.environ.get("AGENT_MEMORY_BASE_URL") or None
    iris_store_id: str | None = os.environ.get("AGENT_MEMORY_STORE_ID") or None
    iris_api_key: str | None = os.environ.get("AGENT_MEMORY_API_KEY") or None
    iris_namespace: str = os.environ.get("CONTEXT_IRIS_NAMESPACE", "context")

    # --- extraction knobs ---
    # PDFs are chunked before extraction so long papers fit the model context and
    # each chunk is reasoned over independently. Sized in characters (~chars/4 tok).
    chunk_chars: int = int(os.environ.get("CONTEXT_CHUNK_CHARS", "12000"))
    chunk_overlap: int = int(os.environ.get("CONTEXT_CHUNK_OVERLAP", "800"))
    max_items_per_chunk: int = int(os.environ.get("CONTEXT_MAX_ITEMS", "12"))

    # --- search ---
    search_top_k: int = int(os.environ.get("CONTEXT_SEARCH_TOP_K", "8"))

    # --- redis key map ---
    item_key_prefix: str = "ctx:item:"
    items_index: str = "ctx:idx:items"


SETTINGS = Settings()
