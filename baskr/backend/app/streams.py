"""Redis Streams surface for the new-papers queue (SPEC §5.5, §6 agent loop).

Thin real helpers over the ``baskr:new_papers`` stream so the ingest path can XADD
new papers and the consumer/agent loop (Phase 6) can read them. Phase 1 only needs
enough to push entries and health-check queue length; consumer-group plumbing lands
with the agent loop.
"""

from __future__ import annotations

from typing import Any

from .config import SETTINGS, Settings
from .redis_client import get_client

NEW_PAPERS_STREAM = "baskr:new_papers"


def add_new_paper(fields: dict[str, Any], settings: Settings = SETTINGS,
                  stream: str = NEW_PAPERS_STREAM) -> str:
    """XADD a new-paper notification; return the generated stream id.

    Values are coerced to strings so any JSON-ish payload round-trips through the
    stream entry without surprising redis-py.
    """
    entry = {k: (v if isinstance(v, (str, bytes, int, float)) else str(v))
             for k, v in fields.items()}
    msg_id = get_client(settings).xadd(stream, entry)
    return msg_id.decode() if isinstance(msg_id, bytes) else msg_id


def stream_length(settings: Settings = SETTINGS,
                  stream: str = NEW_PAPERS_STREAM) -> int:
    """XLEN of the stream (0 if it does not exist yet)."""
    return int(get_client(settings).xlen(stream))
