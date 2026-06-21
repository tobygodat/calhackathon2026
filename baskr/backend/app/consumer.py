"""Background two-stage consumer over the Redis Streams pipeline.

The consumer runs as daemon threads (not coroutines) so it can use the
synchronous Redis client without blocking the uvicorn event loop. It communicates
results back to the async SSE endpoint via a thread-safe in-memory alert store.

Two stages, two batches (see ``batches.py``):

    Stage 1 — vector search  (drains the ``baskr:new_papers`` batch)
        XREAD baskr:new_papers (blocking, 2 s timeout)
        for each newly *seen* paper:
            parse → embed abstract → vector-relevance gate vs the lab profile
            → if it clears the gate, XADD onto the ``baskr:llm_queue`` batch
              (otherwise drop it; the LLM never sees it)

    Stage 2 — LLM scan  (drains the ``baskr:llm_queue`` batch)
        XREAD baskr:llm_queue (blocking, 2 s timeout)
        for each gate survivor:
            classify_paper → if NOT_RELEVANT: skip, else push alert

Splitting the old single loop in two means the cheap vector gate and the expensive
Claude scan run, backpressure, and are observed independently, and the dashboard
can show how much work is parked in each batch at any moment.
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

# Maximum alerts kept in memory (degraded-mode fallback store).
_MAX_ALERTS = 100

# Durable, cross-instance alert log. Each fired alert is one XADD entry whose
# single ``data`` field holds the full alert JSON. Approximate MAXLEN keeps the
# stream bounded without an exact (and slower) trim on every write.
ALERTS_STREAM = "baskr:alerts"
_ALERTS_MAXLEN = 500

# Thread-safe alert store (most recent first is not guaranteed — appended in order).
# Used as a fallback when Redis is unreachable so local dev / tests still see alerts.
_alerts: deque[dict[str, Any]] = deque(maxlen=_MAX_ALERTS)
_lock = threading.Lock()

# ISO-8601 timestamp of the last successful XREAD loop, or None if never run.
_last_heartbeat: str | None = None

# Count of alerts fired in the current process lifetime (not windowed).
_alerts_fired: int = 0

# Stage counters (process lifetime) surfaced in /status so the dashboard can show
# how papers flow through the two batches.
_seen_count: int = 0          # papers pulled off the vector-search batch
_vector_passed_count: int = 0  # papers that cleared the vector gate -> LLM batch
_scanned_count: int = 0        # papers pulled off the LLM-scan batch

# Running consumer thread handles (one per stage).
_vector_thread: threading.Thread | None = None
_llm_thread: threading.Thread | None = None
_stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start(settings: Settings = SETTINGS) -> None:
    """Start both consumer stages. Idempotent — no-op if already running."""
    global _vector_thread, _llm_thread
    running = (
        _vector_thread is not None and _vector_thread.is_alive()
        and _llm_thread is not None and _llm_thread.is_alive()
    )
    if running:
        return
    _stop_event.clear()
    _vector_thread = threading.Thread(
        target=_run_vector_stage, args=(settings,), daemon=True,
        name="baskr-consumer-vector",
    )
    _llm_thread = threading.Thread(
        target=_run_llm_stage, args=(settings,), daemon=True,
        name="baskr-consumer-llm",
    )
    _vector_thread.start()
    _llm_thread.start()
    log.info("Consumer started (stages: %s, %s)",
             _vector_thread.name, _llm_thread.name)


def stop() -> None:
    """Signal both consumer stages to stop and wait for them."""
    _stop_event.set()
    for t in (_vector_thread, _llm_thread):
        if t is not None:
            t.join(timeout=5)
    log.info("Consumer stopped")


def stage_counts() -> dict[str, int]:
    """Per-stage lifetime counters for /status (seen / vector-passed / scanned)."""
    return {
        "seen": _seen_count,
        "vector_passed": _vector_passed_count,
        "scanned": _scanned_count,
        "alerts_fired": _alerts_fired,
    }


def get_recent_alerts(n: int = 20) -> list[dict[str, Any]]:
    """Return the most recent N alerts (thread-safe snapshot of the local store)."""
    with _lock:
        alerts = list(_alerts)
    return alerts[-n:]


# ---------------------------------------------------------------------------
# Redis-backed alert stream (durable + cross-instance)
# ---------------------------------------------------------------------------

def _alert_client(settings: Settings = SETTINGS) -> Any:
    """Return a live Redis client for the alerts stream, or None if unreachable.

    Pings once so callers can cheaply decide between the Redis path and the
    in-process deque fallback without catching connection errors mid-stream."""
    try:
        from .redis_client import get_client  # noqa: PLC0415
        client = get_client(settings)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        log.debug("Alerts: Redis unavailable (%s) — using deque fallback", exc)
        return None


def write_alert_to_stream(alert: dict[str, Any], settings: Settings = SETTINGS,
                          client: Any = None) -> str | None:
    """XADD an alert to ``baskr:alerts`` with approximate MAXLEN trim.

    Returns the generated stream id, or None when Redis is unreachable (the
    caller has already mirrored the alert into the in-process deque)."""
    if client is None:
        client = _alert_client(settings)
    if client is None:
        return None
    try:
        msg_id = client.xadd(
            ALERTS_STREAM,
            {"data": json.dumps(alert)},
            maxlen=_ALERTS_MAXLEN,
            approximate=True,
        )
        return msg_id.decode() if isinstance(msg_id, bytes) else msg_id
    except Exception as exc:  # noqa: BLE001
        log.warning("Alerts: XADD to %s failed: %s", ALERTS_STREAM, exc)
        return None


def read_alerts_stream(last_id: str = "0", block_ms: int = 0, count: int = 100,
                       settings: Settings = SETTINGS,
                       client: Any = None) -> tuple[str, list[dict[str, Any]]]:
    """XREAD alerts newer than ``last_id`` from ``baskr:alerts``.

    ``last_id="0"`` replays from the start of the stream. ``block_ms`` of 0 means
    a non-blocking read; a positive value blocks for that many milliseconds.
    Returns ``(new_last_id, [alert_dict, ...])``; on an unreachable Redis returns
    ``(last_id, [])`` so the caller can fall back."""
    if client is None:
        client = _alert_client(settings)
    if client is None:
        return last_id, []
    try:
        entries = client.xread({ALERTS_STREAM: last_id},
                               block=(block_ms or None), count=count)
    except Exception as exc:  # noqa: BLE001
        # A blocking XREAD whose idle wait exceeds the client socket_timeout raises
        # a socket TimeoutError — that just means "no new alerts yet", so surface an
        # empty batch and let the SSE caller heartbeat. Real outages (ConnectionError)
        # re-raise so the caller can fall back to the deque.
        if block_ms and "timeout" in type(exc).__name__.lower():
            return last_id, []
        raise
    alerts: list[dict[str, Any]] = []
    new_last = last_id
    for _stream, messages in entries or []:
        for msg_id, fields in messages:
            new_last = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
            raw = fields.get("data")
            if raw is None:
                raw = fields.get(b"data")
            if isinstance(raw, bytes):
                raw = raw.decode()
            if not raw:
                continue
            try:
                alerts.append(json.loads(raw))
            except Exception:  # noqa: BLE001
                continue
    return new_last, alerts


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
    # Mirror to the durable, cross-instance Redis stream. A Redis outage leaves
    # the alert in the local deque so degraded mode still surfaces it.
    write_alert_to_stream(alert, SETTINGS)


def _paper_to_fields(paper: PaperOut) -> dict[str, str]:
    """Flatten a ``PaperOut`` back to the stream-entry field schema (mirrors
    ``producer._paper_to_fields``) so a gate survivor round-trips onto the LLM
    batch byte-for-byte compatibly with ``_parse_paper``."""
    return {
        "uid": paper.uid or f"{paper.source}:{paper.source_id}",
        "source": paper.source,
        "source_id": paper.source_id,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": json.dumps(paper.authors),
        "doi": paper.doi or "",
        "url": paper.url or "",
        "journal": paper.journal or "",
        "published": paper.published or "",
    }


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


# ---------------------------------------------------------------------------
# Stage 1 — vector-search gate
# ---------------------------------------------------------------------------

def _vector_relevance(paper: PaperOut, settings: Settings) -> float:
    """Cheap vector relevance of ``paper`` to the lab profile (no LLM).

    Embeds the paper abstract and the lab's profile-item texts with the shared
    embedder and returns the best cosine similarity. This is the same notion of
    similarity ``redis_client.query_similar`` uses, but computed locally so it works
    on freshly fetched papers that aren't indexed yet (and in degraded mode via the
    keyless hash embedder).

    Returns a similarity in ``[0, 1]``, or ``1.0`` when relevance can't be assessed
    (no profile items / embedding failure) so the gate fails *open* — a transient
    embedding problem must never silently starve the LLM stage.
    """
    from . import memory  # noqa: PLC0415
    from .engine import _cosine  # noqa: PLC0415

    text = (paper.abstract or paper.title or "").strip()
    if not text:
        return 0.0
    try:
        items = memory.load_profile(settings).items
        item_texts = [it.text for it in items if getattr(it, "text", "")]
        if not item_texts:
            return 1.0  # nothing to gate against -> let it through

        from .embeddings import embed_batch, embed_text  # noqa: PLC0415

        paper_vec = embed_text(text, settings)
        item_vecs = embed_batch(item_texts, settings)
        if not paper_vec or not item_vecs:
            return 1.0
        return max(_cosine(paper_vec, v) for v in item_vecs)
    except Exception as exc:  # noqa: BLE001 — gate fails open on any error
        log.debug("vector gate: relevance unavailable (%s) — passing through", exc)
        return 1.0


def _vector_gate(paper: PaperOut, settings: Settings) -> bool:
    """True if ``paper`` clears the vector-relevance threshold for LLM scanning."""
    score = _vector_relevance(paper, settings)
    return score >= settings.vector_gate_threshold


def _run_vector_stage(settings: Settings) -> None:
    """Drain the vector-search batch; enqueue gate survivors to the LLM batch."""
    global _seen_count, _vector_passed_count
    from .batches import VECTOR_QUEUE_STREAM, enqueue_for_llm  # noqa: PLC0415
    from .redis_client import get_client  # noqa: PLC0415

    last_id = "0-0"  # read from the beginning of the stream
    log.info("Consumer[vector]: reading %s from %s", VECTOR_QUEUE_STREAM, last_id)

    while not _stop_event.is_set():
        try:
            client = get_client(settings)
            entries = client.xread(
                {VECTOR_QUEUE_STREAM: last_id},
                block=2000,  # 2 s timeout so we can check _stop_event
                count=10,
            )
            _update_heartbeat()
            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    paper = _parse_paper(fields)
                    if not paper:
                        continue
                    _seen_count += 1
                    if _vector_gate(paper, settings):
                        _vector_passed_count += 1
                        try:
                            enqueue_for_llm(_paper_to_fields(paper), settings)
                        except Exception as exc:  # noqa: BLE001
                            log.warning("Consumer[vector]: enqueue failed: %s", exc)
                    else:
                        log.debug("Consumer[vector]: %s below threshold (drop)",
                                  paper.title[:40])
        except Exception as exc:  # noqa: BLE001
            log.warning("Consumer[vector] loop error: %s — retrying in 2 s", exc)
            _update_heartbeat()
            time.sleep(2)


# ---------------------------------------------------------------------------
# Stage 2 — LLM scan
# ---------------------------------------------------------------------------

def _run_llm_stage(settings: Settings) -> None:
    """Drain the LLM-scan batch; classify each paper and alert on relevance."""
    global _scanned_count
    from .batches import LLM_QUEUE_STREAM  # noqa: PLC0415
    from .redis_client import get_client  # noqa: PLC0415

    last_id = "0-0"
    log.info("Consumer[llm]: reading %s from %s", LLM_QUEUE_STREAM, last_id)

    while not _stop_event.is_set():
        try:
            client = get_client(settings)
            entries = client.xread(
                {LLM_QUEUE_STREAM: last_id},
                block=2000,
                count=10,
            )
            _update_heartbeat()
            if not entries:
                continue

            for _stream, messages in entries:
                for msg_id, fields in messages:
                    last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    paper = _parse_paper(fields)
                    if paper:
                        _scanned_count += 1
                        _classify_and_alert(paper, settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("Consumer[llm] loop error: %s — retrying in 2 s", exc)
            _update_heartbeat()
            time.sleep(2)
