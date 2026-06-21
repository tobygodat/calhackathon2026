"""The two in-flight pipeline batches (SPEC §6 agent loop, two-stage).

At any moment the live pipeline holds work in two distinct batches:

1. **Vector-search batch** — newly *seen* papers waiting to be vector searched
   (the relevance gate). This is the existing ``baskr:new_papers`` stream the
   producer XADDs onto; the vector-search stage of the consumer drains it.
2. **LLM-scan batch** — papers that already *passed* the vector search and are
   waiting to be scanned (classified) by the LLM. This is the new
   ``baskr:llm_queue`` stream the vector-search stage XADDs onto and the LLM stage
   drains.

Splitting the old single-stage consumer into these two batches means the cheap
vector relevance gate and the expensive Claude classification can run, backpressure,
and be observed independently — and the dashboard can show how much work is parked
in each stage.

This module is a thin, degrade-safe Redis-Streams surface (mirrors ``streams.py``):
size accessors return 0 when Redis is unreachable rather than raising.
"""

from __future__ import annotations

from typing import Any

from .config import SETTINGS, Settings
from .streams import NEW_PAPERS_STREAM, add_new_paper, stream_length

# Batch 2: papers that passed the vector-search gate, awaiting LLM classification.
LLM_QUEUE_STREAM = "baskr:llm_queue"

# Batch 1 alias (papers awaiting vector search) — the producer's intake stream.
VECTOR_QUEUE_STREAM = NEW_PAPERS_STREAM


def enqueue_for_llm(fields: dict[str, Any], settings: Settings = SETTINGS) -> str:
    """XADD a vector-search survivor onto the LLM-scan batch; return its stream id."""
    return add_new_paper(fields, settings, stream=LLM_QUEUE_STREAM)


def vector_queue_length(settings: Settings = SETTINGS) -> int:
    """Papers currently parked in the vector-search batch (0 if Redis is down)."""
    try:
        return stream_length(settings, stream=VECTOR_QUEUE_STREAM)
    except Exception:  # noqa: BLE001
        return 0


def llm_queue_length(settings: Settings = SETTINGS) -> int:
    """Papers currently parked in the LLM-scan batch (0 if Redis is down)."""
    try:
        return stream_length(settings, stream=LLM_QUEUE_STREAM)
    except Exception:  # noqa: BLE001
        return 0


def batch_sizes(settings: Settings = SETTINGS) -> dict[str, int]:
    """Both batch depths in one call, for the ``/status`` metrics payload."""
    return {
        "vector_search": vector_queue_length(settings),
        "llm_scan": llm_queue_length(settings),
    }
