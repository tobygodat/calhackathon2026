"""FastAPI app + all routes (SPEC §8).

Route surface (CORS open to the Vite dev origin, no auth):

    GET  /api/health            -> {"status": "ok"}
    GET  /status                -> dashboard health (see dev-ui/README.md)
    GET  /api/profile           -> Profile
    POST /api/search            -> list[SearchHit]   (<=5, live)
    GET  /api/digest/history    -> list[DigestSummary]
    GET  /api/digest/{date}     -> list[DigestEntry] (frozen)
    POST /api/profile/memory    -> Profile           (stretch)
    POST /api/pipeline/search   -> PipelineSearchResult  (dev UI pipeline panel)
    GET  /api/alerts/stream     -> SSE text/event-stream of classification alerts
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import consumer, engine, memory, pipeline_state
from . import status as status_probe
from .config import SETTINGS
from .ingest import fetch_raw
from .models import (
    DigestEntry,
    DigestSummary,
    MemoryWriteRequest,
    PipelineSearchRequest,
    PipelineSearchResult,
    Profile,
    SearchHit,
    SearchRequest,
)
from .redis_client import get_client, load_digest


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ANN001
    """Start the stream consumer on boot; stop it on shutdown."""
    consumer.start(SETTINGS)
    yield
    consumer.stop()


app = FastAPI(title="Baskr", version="0.0.1", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Filesystem path to frozen digest files relative to the baskr/ root.
_FROZEN_DIR = Path(__file__).resolve().parents[2] / "data" / "digest_frozen"


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, Any]:
    """Dashboard health/metrics for the dev UI (shape: dev-ui/README.md).

    Degraded-mode safe: probes never raise, so this always returns 200 even when
    Redis is down or API keys are unset.
    """
    return status_probe.get_status()


@app.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    return memory.load_profile(SETTINGS)


@app.post("/api/search", response_model=list[SearchHit])
def search(body: SearchRequest) -> list[SearchHit]:
    """Live search: fetch recent papers, classify against the lab profile, return top hits."""
    return engine.active_search(body.question, SETTINGS)


@app.get("/api/digest/history", response_model=list[DigestSummary])
def digest_history() -> list[DigestSummary]:
    """Scan Redis and the frozen-digest directory; return one summary per date."""
    summaries: dict[str, DigestSummary] = {}

    # 1. Redis-backed digests.
    try:
        client = get_client(SETTINGS)
        for key in client.keys(f"{SETTINGS.digest_key_prefix}*"):
            raw_key = key.decode() if isinstance(key, bytes) else key
            date = raw_key[len(SETTINGS.digest_key_prefix):]
            raw = load_digest(date, SETTINGS)
            if raw is None:
                continue
            summary = _digest_summary(date, raw)
            if summary:
                summaries[date] = summary
    except Exception:  # noqa: BLE001  (degraded: no Redis)
        pass

    # 2. Filesystem frozen digests (offline / seed fallback).
    if _FROZEN_DIR.exists():
        for path in _FROZEN_DIR.glob("*.json"):
            date = path.stem
            if date in summaries:
                continue
            try:
                summary = _digest_summary(date, path.read_text())
                if summary:
                    summaries[date] = summary
            except Exception:  # noqa: BLE001
                continue

    return sorted(summaries.values(), key=lambda s: s.date, reverse=True)


def _digest_summary(date: str, raw_json: str) -> DigestSummary | None:
    """Parse raw digest JSON and return a DigestSummary, or None on error."""
    try:
        entries = json.loads(raw_json)
        if not isinstance(entries, list) or not entries:
            return None
        labels = [e["classification"]["label"] for e in entries if "classification" in e]
        top_label = Counter(labels).most_common(1)[0][0] if labels else "TANGENTIAL"
        return DigestSummary(date=date, count=len(entries), top_label=top_label)
    except Exception:  # noqa: BLE001
        return None


@app.get("/api/digest/{date}", response_model=list[DigestEntry])
def digest_for_date(date: str) -> list[DigestEntry]:
    """Return the frozen digest for ``date`` (YYYY-MM-DD). 404 if not found."""
    # 1. Try Redis.
    try:
        raw = load_digest(date, SETTINGS)
        if raw is not None:
            return [DigestEntry(**e) for e in json.loads(raw)]
    except Exception:  # noqa: BLE001
        pass

    # 2. Try filesystem.
    frozen_path = _FROZEN_DIR / f"{date}.json"
    if frozen_path.exists():
        try:
            return [DigestEntry(**e) for e in json.loads(frozen_path.read_text())]
        except Exception:  # noqa: BLE001
            pass

    raise HTTPException(status_code=404, detail=f"No digest found for {date!r}")


@app.post("/api/profile/memory", response_model=Profile)
def add_memory(body: MemoryWriteRequest) -> Profile:
    """Append a finding to the lab profile (stretch: memory grows visibly)."""
    return memory.append_item(body.kind, body.text, SETTINGS)


@app.post("/api/pipeline/search", response_model=PipelineSearchResult)
def pipeline_search(body: PipelineSearchRequest) -> PipelineSearchResult:
    """Dev UI pipeline panel: raw paper fetch from configured sources.

    Returns papers + per-source counts + any source errors. Also updates the
    pipeline metrics that ``/status`` surfaces.
    """
    papers, counts, errors = fetch_raw(
        body.query, body.days, body.max_results, SETTINGS
    )

    # Filter by requested sources if the caller specified a subset.
    if body.sources:
        wanted = set(body.sources)
        papers = [p for p in papers if p.source in wanted]

    # Compute cross-source dedupe ratio: sum(pre-dedup per-source counts) vs final count.
    pre_dedup = sum(v for k, v in counts.items() if k != "staged")
    post_dedup = len(papers)
    dedupe_ratio = (pre_dedup - post_dedup) / pre_dedup if pre_dedup > 0 else 0.0

    pipeline_state.update(
        query=body.query,
        result_count=post_dedup,
        source_counts=counts,
        source_errors=errors,
        dedupe_ratio=dedupe_ratio,
    )

    return PipelineSearchResult(papers=papers, counts=counts, errors=errors)


@app.get("/api/alerts/stream")
async def alerts_stream():
    """SSE endpoint: streams classification alerts fired by the background consumer.

    Each event is a JSON object: {paper_title, label, reason, confidence, fired_at}.
    Yields a heartbeat comment every second to keep the connection alive.
    """

    async def _generate():
        sent = 0
        while True:
            alerts = consumer.get_recent_alerts()
            if len(alerts) > sent:
                for alert in alerts[sent:]:
                    yield f"data: {json.dumps(alert)}\n\n"
                sent = len(alerts)
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
