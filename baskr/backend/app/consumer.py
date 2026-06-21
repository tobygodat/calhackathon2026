"""Background asyncio-safe consumer over the ``baskr:new_papers`` Redis stream.

The consumer runs as a daemon thread (not a coroutine) so it can use the
synchronous Redis client without blocking the uvicorn event loop. It communicates
results back to the async SSE endpoint via a thread-safe in-memory alert store.

Loop:
    XREAD baskr:new_papers (blocking, 2 s timeout)
    for each entry:
        parse → embed abstract → retrieve_relevant (top-k memory)
        → classify_paper → if NOT_RELEVANT: skip, else push alert
    update heartbeat
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from collections import deque
from typing import Any

from .config import SETTINGS, Settings
from .models import PaperOut

log = logging.getLogger("baskr.consumer")

# Maximum alerts kept in memory.
_MAX_ALERTS = 100

# Thread-safe alert store (most recent first is not guaranteed — appended in order).
_alerts: deque[dict[str, Any]] = deque(maxlen=_MAX_ALERTS)
_lock = threading.Lock()

# ISO-8601 timestamp of the last successful XREAD loop, or None if never run.
_last_heartbeat: str | None = None

# Count of alerts fired in the current process lifetime (not windowed).
_alerts_fired: int = 0

# Running consumer thread handle.
_thread: threading.Thread | None = None
_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(settings: Settings = SETTINGS) -> None:
    """Start the consumer thread. Idempotent — no-op if already running."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_consumer, args=(settings,), daemon=True, name="baskr-consumer"
    )
    _thread.start()
    log.info("Consumer started (thread %s)", _thread.name)


def stop() -> None:
    """Signal the consumer thread to stop and wait for it."""
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)
    log.info("Consumer stopped")


def get_recent_alerts(n: int = 20) -> list[dict[str, Any]]:
    """Return the most recent N alerts (thread-safe snapshot)."""
    with _lock:
        alerts = list(_alerts)
    return alerts[-n:]


def last_heartbeat() -> str | None:
    """ISO-8601 timestamp of the last XREAD loop, or None."""
    return _last_heartbeat


def alerts_fired_count() -> int:
    """Total alerts fired in this process."""
    return _alerts_fired


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _update_heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = datetime.datetime.utcnow().isoformat() + "Z"


def _push_alert(alert: dict[str, Any]) -> None:
    global _alerts_fired
    with _lock:
        _alerts.append(alert)
        _alerts_fired += 1


def _parse_paper(fields: dict[bytes | str, bytes | str]) -> PaperOut | None:
    """Reconstruct a PaperOut from Redis stream hash fields."""
    def _decode(v: bytes | str) -> str:
        return v.decode() if isinstance(v, bytes) else v

    def _key(k: bytes | str) -> str:
        return k.decode() if isinstance(k, bytes) else k

    f = {_key(k): _decode(v) for k, v in fields.items()}
    try:
        return PaperOut(
            source=f.get("source", "unknown"),
            source_id=f.get("source_id", ""),
            title=f.get("title", ""),
            abstract=f.get("abstract", ""),
            authors=json.loads(f["authors"]) if "authors" in f else [],
            doi=f.get("doi") or None,
            url=f.get("url") or None,
            journal=f.get("journal") or None,
            published=f.get("published") or None,
            uid=f.get("uid") or None,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Consumer: could not parse paper from stream fields: %s", exc)
        return None


def _classify_and_alert(paper: PaperOut, settings: Settings) -> None:
    """Classify one paper; push an alert if it is relevant."""
    from . import memory  # noqa: PLC0415  (avoid circular at import)
    from .engine import classify_paper  # noqa: PLC0415

    try:
        profile = memory.load_profile(settings)
        classification = classify_paper(paper, profile, settings)
        if classification.label.value == "NOT_RELEVANT":
            log.debug("Consumer: %s → NOT_RELEVANT (skip)", paper.title[:40])
            return

        alert = {
            "paper_title": paper.title,
            "paper_source": paper.source,
            "paper_url": paper.url,
            "label": classification.label.value,
            "reason": classification.reason,
            "confidence": classification.confidence,
            "matched_item_id": classification.matched_item_id,
            "fired_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        _push_alert(alert)
        log.info(
            "Consumer: ALERT %s → %s (conf %.2f) — %s",
            paper.title[:40],
            classification.label.value,
            classification.confidence,
            classification.reason[:60],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Consumer: classify failed for %r: %s", paper.title[:40], exc)


def _run_consumer(settings: Settings) -> None:
    """Main consumer loop (runs in daemon thread)."""
    from .redis_client import get_client  # noqa: PLC0415

    last_id = "0-0"  # read from the beginning of the stream
    log.info("Consumer: reading baskr:new_papers from %s", last_id)

    while not _stop_event.is_set():
        try:
            client = get_client(settings)
            entries = client.xread(
                {"baskr:new_papers": last_id},
                block=2000,  # 2 s timeout so we can check _stop_event
                count=10,
            )
            _update_heartbeat()

            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    raw_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    last_id = raw_id
                    paper = _parse_paper(fields)
                    if paper:
                        _classify_and_alert(paper, settings)

        except Exception as exc:  # noqa: BLE001
            log.warning("Consumer loop error: %s — retrying in 2 s", exc)
            _update_heartbeat()
            time.sleep(2)
