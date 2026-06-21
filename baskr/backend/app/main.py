"""FastAPI app + all routes (SPEC §8).

Route surface:
    GET  /api/health            -> {"status": "ok"}
    GET  /api/profile           -> Profile
    POST /api/profile/memory    -> Profile           (stretch)

Dev-UI routes (every route lives under /api; the vite proxy forwards as-is):
    GET  /api/status            -> system status for dev-ui
    GET  /api/ledger            -> paper ledger (newest first)
    POST /api/intake            -> drop file(s) of papers onto the intake stream
"""

from __future__ import annotations

import json
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from . import engine, memory
from .config import SETTINGS
from .models import (
    DigestEntry,
    DigestSummary,
    Label,
    MemoryWriteRequest,
    PaperOut,
    Profile,
    SearchHit,
    SearchRequest,
)
from .redis_client import get_client, load_digest

# Frozen-digest filesystem directory (app/ -> backend/ -> baskr/ -> data/digest_frozen).
_FROZEN_DIR = Path(__file__).resolve().parents[2] / "data" / "digest_frozen"

# ---------------------------------------------------------------------------
# PubMed probe result cache
#
# Without this, every /status poll fires a fresh unauthenticated NCBI request.
# Concurrent polls race in ThreadPoolExecutor: if one times out and another
# succeeds in the same second, record_status() sees two different ok values and
# writes an off/on flip pair — generating 4-5× more CSV rows than any other
# source. A 30s TTL collapses all concurrent polls to one NCBI hit and
# eliminates the oscillation.
# ---------------------------------------------------------------------------
_pubmed_cache_lock = threading.Lock()
_pubmed_cache_result: "dict | None" = None
_pubmed_cache_expires: float = 0.0
_PUBMED_CACHE_TTL = 30.0


def _pubmed_probe() -> dict:
    """Return NCBI reachability probe result, using a 30s in-process cache.

    Only successful responses are cached. A network failure raises normally so
    ``_probe()`` can mark the connection down — but the failure never evicts a
    valid cached entry.
    """
    global _pubmed_cache_result, _pubmed_cache_expires
    now = time.monotonic()
    with _pubmed_cache_lock:
        if _pubmed_cache_result is not None and now < _pubmed_cache_expires:
            return _pubmed_cache_result
    import requests  # noqa: PLC0415  (lazy: keep boot light)
    r = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
        params={"retmode": "json"}, timeout=8,
    )
    r.raise_for_status()
    result: dict = {}
    with _pubmed_cache_lock:
        _pubmed_cache_result = result
        _pubmed_cache_expires = time.monotonic() + _PUBMED_CACHE_TTL
    return result


def _reset_pubmed_cache() -> None:
    """Clear the PubMed probe cache. Used by tests."""
    global _pubmed_cache_result, _pubmed_cache_expires
    with _pubmed_cache_lock:
        _pubmed_cache_result = None
        _pubmed_cache_expires = 0.0


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Record the backend turning on/off in the service status log."""
    from .monitoring import record_backend_event
    try:
        record_backend_event("on")
    except Exception:
        pass
    yield
    try:
        record_backend_event("off")
    except Exception:
        pass


app = FastAPI(title="Baskr", version="0.1.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Make system_pieces importable  (app/ -> backend/ -> baskr/ -> calhackathon2026/)
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Baskr API
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    return memory.load_profile(SETTINGS)


@app.post("/api/profile/memory", response_model=Profile)
def add_memory(body: MemoryWriteRequest) -> Profile:
    return memory.append_item(body.kind, body.text, SETTINGS)


@app.post("/api/search", response_model=list[SearchHit])
def search(body: SearchRequest) -> list[SearchHit]:
    return engine.active_search(body.question, SETTINGS)


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

@app.get("/api/digest/history", response_model=list[DigestSummary])
def digest_history() -> list[DigestSummary]:
    """Summaries of every frozen digest on the filesystem, plus any in Redis."""
    from collections import Counter

    summaries: dict[str, DigestSummary] = {}

    # Filesystem-backed frozen digests.
    if _FROZEN_DIR.exists():
        for path in sorted(_FROZEN_DIR.glob("*.json")):
            try:
                entries = json.loads(path.read_text())
            except Exception:
                continue
            if not isinstance(entries, list):
                continue
            labels = [
                e["classification"]["label"]
                for e in entries
                if isinstance(e, dict) and e.get("classification")
            ]
            top_label = Counter(labels).most_common(1)[0][0] if labels else Label.NOT_RELEVANT
            summaries[path.stem] = DigestSummary(
                date=path.stem, count=len(entries), top_label=Label(top_label)
            )

    # Redis-backed digests.
    try:
        client = get_client(SETTINGS)
        keys = client.keys("baskr:digest:*")
        for key in keys or []:
            date = key.decode() if isinstance(key, bytes) else str(key)
            date = date.rsplit(":", 1)[-1]
            if date in summaries:
                continue
            payload = load_digest(date, SETTINGS)
            if not payload:
                continue
            try:
                entries = json.loads(payload)
            except Exception:
                continue
            if not isinstance(entries, list):
                continue
            labels = [
                e["classification"]["label"]
                for e in entries
                if isinstance(e, dict) and e.get("classification")
            ]
            top_label = Counter(labels).most_common(1)[0][0] if labels else Label.NOT_RELEVANT
            summaries[date] = DigestSummary(
                date=date, count=len(entries), top_label=Label(top_label)
            )
    except Exception:
        pass

    return [summaries[d] for d in sorted(summaries)]


@app.get("/api/digest/{date}", response_model=list[DigestEntry])
def digest_for_date(date: str) -> list[DigestEntry]:
    """Return all entries for a single date, filesystem first then Redis."""
    fs_path = _FROZEN_DIR / f"{date}.json"
    if fs_path.exists():
        entries = json.loads(fs_path.read_text())
        return [DigestEntry(**e) for e in entries]

    # Redis-backed digest. A Redis outage degrades to "no digest" (404), matching
    # digest_history's offline-safe handling rather than surfacing a 500.
    try:
        payload = load_digest(date, SETTINGS)
    except Exception:
        payload = None
    if payload:
        entries = json.loads(payload)
        return [DigestEntry(**e) for e in entries]

    raise HTTPException(status_code=404, detail=f"No digest for {date}")


# ---------------------------------------------------------------------------
# Pipeline search (dev-ui)
# ---------------------------------------------------------------------------

def fetch_raw(query: str, days: int, max_results: int, settings) -> tuple[list[PaperOut], dict, dict]:
    """Fetch raw papers across sources. Wraps the DataPipeline; degrades to
    ([], {}, {"pipeline": str(exc)}) on any error."""
    try:
        from system_pieces.data_pipeline import DataPipeline  # noqa: PLC0415

        pipeline = DataPipeline()
        result = pipeline.fetch(query, days=days, max_per_source=max_results)
        papers = [PaperOut(**p.to_dict()) for p in result.papers]
        return papers, dict(result.counts), dict(result.errors)
    except Exception as exc:  # noqa: BLE001
        return [], {}, {"pipeline": str(exc)}


@app.get("/api/thumbnail")
def thumbnail(source: str, url: str | None = None) -> Response:
    """First page of the paper's PDF as a PNG, derived from source + url.

    Returns 404 (never 500) when no thumbnail can be produced so the frontend
    falls back to its placeholder skeleton.
    """
    from .thumbnails import render_thumbnail
    png = render_thumbnail(source, url)
    if png is None:
        raise HTTPException(status_code=404, detail="No thumbnail available")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.post("/api/profile/memory", response_model=Profile)
def add_memory(body: MemoryWriteRequest) -> Profile:
    """Append a finding to the lab profile (stretch: memory grows visibly)."""
    return memory.append_item(body.kind, body.text, SETTINGS)


@app.post("/api/pipeline/search")
def pipeline_search(body: dict) -> dict:
    query = body.get("query") or "gut microbiome"
    days = int(body.get("days", 7))
    max_results = int(body.get("max_results", 50))
    sources = body.get("sources")

    papers, counts, errors = fetch_raw(query, days, max_results, SETTINGS)

    if sources:
        papers = [p for p in papers if p.source in sources]

    return {
        "papers": [p.model_dump() for p in papers],
        "counts": counts,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Alerts SSE stream
# ---------------------------------------------------------------------------

# Idle gap before the blocking reader emits an SSE heartbeat comment (ms).
_SSE_HEARTBEAT_MS = 15000


def _redis_alert_gen(consumer, client):
    """Stream alerts from the Redis ``baskr:alerts`` stream.

    Replays everything already in the stream (so a freshly connected client sees
    existing alerts immediately — survives restarts and spans backend instances),
    then blocks for new entries, emitting a heartbeat comment when idle."""
    last_id = "0"  # replay from the very start of the stream
    last_id, alerts = consumer.read_alerts_stream(last_id, block_ms=0, client=client)
    for alert in alerts:
        yield f"data: {json.dumps(alert)}\n\n"
    while True:
        try:
            last_id, alerts = consumer.read_alerts_stream(
                last_id, block_ms=_SSE_HEARTBEAT_MS, client=client
            )
        except Exception:
            break
        if not alerts:
            yield ": heartbeat\n\n"
            continue
        for alert in alerts:
            yield f"data: {json.dumps(alert)}\n\n"


def _deque_alert_gen(consumer):
    """Degraded fallback: emit the in-process deque snapshot once (no Redis)."""
    try:
        alerts = consumer.get_recent_alerts()
    except Exception:
        alerts = []
    for alert in alerts:
        try:
            yield f"data: {json.dumps(alert)}\n\n"
        except Exception:
            continue


@app.get("/api/alerts/stream")
def alerts_stream() -> StreamingResponse:
    """Server-sent events stream of alerts.

    Backed by the Redis ``baskr:alerts`` stream so alerts survive a backend
    restart and are shared across replicas behind a load balancer. Falls back to
    the in-process deque when Redis is unreachable. Offline-safe."""

    def _gen():
        from . import consumer
        client = consumer._alert_client(SETTINGS)
        if client is not None:
            yield from _redis_alert_gen(consumer, client)
        else:
            yield from _deque_alert_gen(consumer)

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Paper ledger
# ---------------------------------------------------------------------------

@app.get("/api/ledger")
def ledger() -> list[dict]:
    """Return the paper ledger newest-first.

    Each entry: ``{"title": str, "first_seen_at": str (ISO-8601 Z), "source": str}``.
    """
    from .monitoring import paper_ledger
    return paper_ledger()


# ---------------------------------------------------------------------------
# Intake (testing feature: drop file(s) of papers onto the intake stream)
# ---------------------------------------------------------------------------

def _paper_fields(paper: dict) -> dict[str, str]:
    """Flatten a paper dict to the stream-entry field schema the consumer expects.

    Mirrors ``producer._paper_to_fields``: authors are JSON-encoded and every
    missing field defaults to "".
    """
    source = str(paper.get("source", "") or "")
    source_id = str(paper.get("source_id", "") or "")
    uid = paper.get("uid") or (f"{source}:{source_id}" if (source or source_id) else "")
    authors = paper.get("authors") or []
    return {
        "uid": uid,
        "source": source,
        "source_id": source_id,
        "title": str(paper.get("title", "") or ""),
        "abstract": str(paper.get("abstract", "") or ""),
        "authors": json.dumps(authors),
        "doi": str(paper.get("doi", "") or ""),
        "url": str(paper.get("url", "") or ""),
        "journal": str(paper.get("journal", "") or ""),
        "published": str(paper.get("published", "") or ""),
    }


@app.post("/api/intake")
async def intake(files: list[UploadFile]) -> dict:
    """Accept one or more uploaded JSON files (single paper object or array of
    them) and push each paper onto the intake stream + paper ledger.

    Offline-safe: a Redis outage records the paper to the ledger and notes the
    error, but never 500s the request.
    """
    from . import monitoring, streams

    streamed = 0
    recorded = 0
    skipped = 0
    errors: dict[str, str] = {}
    ids: list[str] = []

    for upload in files:
        name = upload.filename or "file"
        try:
            raw = await upload.read()
            data = json.loads(raw)
        except Exception as exc:
            errors[name] = f"could not parse JSON: {exc}"
            continue

        papers = data if isinstance(data, list) else [data]
        for idx, paper in enumerate(papers):
            if not isinstance(paper, dict):
                errors[f"{name}[{idx}]"] = "not a JSON object"
                skipped += 1
                continue
            title = (paper.get("title") or "").strip()
            if not title:
                skipped += 1
                continue

            # Ledger (always, even if Redis is down).
            try:
                monitoring.record_papers([paper])
                recorded += 1
            except Exception as exc:
                errors[f"{name}[{idx}]:ledger"] = str(exc)

            # Stream (offline-safe).
            try:
                msg_id = streams.add_new_paper(_paper_fields(paper))
                ids.append(msg_id)
                streamed += 1
            except Exception as exc:
                errors[f"{name}[{idx}]:stream"] = str(exc)

    return {
        "streamed": streamed,
        "recorded": recorded,
        "skipped": skipped,
        "errors": errors,
        "ids": ids,
    }


# ---------------------------------------------------------------------------
# Dev-UI routes
# ---------------------------------------------------------------------------

def _probe(fn) -> dict:
    """Run a probe fn. On success returns {ok, latency_ms, **(fn's dict or {})};
    a probe may return a dict of extra fields (e.g. {"detail": "842 docs"})."""
    t0 = time.monotonic()
    try:
        extra = fn() or {}
        result = {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
        if isinstance(extra, dict):
            result.update(extra)
        return result
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:200]}


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@app.get("/api/status")
def system_status() -> dict:
    """Honest system status for the dev monitor.

    Probes every service the backend actually relies on (data sources, Redis,
    external APIs) concurrently, and reports metrics derived from the real code
    and data — not hardcoded. The redis_sources list reflects the Redis surfaces
    that are genuinely reachable right now.
    """
    from .config import SETTINGS

    # Holder for extra metrics a probe discovers (e.g. live RedisVL doc count).
    discovered: dict = {}

    # --- data sources --------------------------------------------------------
    def ping_pubmed():
        return _pubmed_probe()

    def ping_arxiv():
        import requests
        r = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": "all:microbiome", "max_results": 1}, timeout=6,
        )
        r.raise_for_status()

    def ping_biorxiv():
        import requests
        r = requests.get("https://api.biorxiv.org/details/biorxiv/2024-01-01/2024-01-02/0",
                         timeout=6)
        r.raise_for_status()

    def ping_openalex():
        import requests
        r = requests.get("https://api.openalex.org/works",
                         params={"per-page": 1, "mailto": "baskr@example.com"}, timeout=6)
        r.raise_for_status()

    def ping_chemrxiv():
        import requests
        r = requests.get("https://chemrxiv.org/engage/chemrxiv/public-api/v1/items",
                         params={"limit": 1}, timeout=6)
        r.raise_for_status()

    def ping_medrxiv():
        import requests
        r = requests.get("https://api.medrxiv.org/details/medrxiv/2024-01-01/2024-01-02/0",
                         timeout=6)
        r.raise_for_status()

    # --- redis surfaces ------------------------------------------------------
    def ping_redis():
        import redis as _r
        c = _r.from_url(SETTINGS.redis_url, socket_timeout=2,
                        socket_connect_timeout=2, decode_responses=True)
        try:
            c.ping()
        finally:
            try:
                c.close()
            except Exception:
                pass

    def probe_redisvl():
        """Detect whether the Redis Query Engine (search module) is available and,
        if so, report the papers index doc count."""
        import redis as _r
        c = _r.from_url(SETTINGS.redis_url, socket_timeout=2,
                        socket_connect_timeout=2, decode_responses=True)
        try:
            modules = c.execute_command("MODULE", "LIST") or []
            names: list[str] = []
            for m in modules:
                if isinstance(m, dict):
                    names.append(str(m.get("name", "")).lower())
                elif isinstance(m, (list, tuple)):
                    for i in range(0, len(m) - 1, 2):
                        if str(m[i]).lower() == "name":
                            names.append(str(m[i + 1]).lower())
            if not any("search" in n for n in names):
                raise RuntimeError("Redis Query Engine (search module) not loaded")
            # Index doc count, best effort.
            try:
                info = c.execute_command("FT.INFO", SETTINGS.papers_index)
                num = 0
                for i in range(0, len(info) - 1, 2):
                    if str(info[i]) == "num_docs":
                        num = int(info[i + 1])
                        break
                discovered["corpus_index_docs"] = num
                return {"detail": f"{num} docs"}
            except Exception:
                discovered["corpus_index_docs"] = 0
                return {"detail": "index not created"}
        finally:
            try:
                c.close()
            except Exception:
                pass

    # --- external APIs -------------------------------------------------------
    def ping_anthropic():
        if not SETTINGS.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic
        Anthropic(api_key=SETTINGS.anthropic_api_key).models.list()
        return {"detail": SETTINGS.reason_model or "claude (default)"}

    def ping_consumer():
        # The FastAPI process is, by definition, alive and answering this request.
        return {"detail": "FastAPI online"}

    # --- feature-level Redis surfaces (dashboard contract) -------------------
    def ping_streams():
        from .streams import stream_length
        n = stream_length(SETTINGS)
        discovered["stream_length"] = n
        return {"detail": f"{n} queued"}

    def ping_agent_memory():
        from .memory import profile_item_count
        n = profile_item_count(SETTINGS)
        return {"detail": f"{n} records"}

    def ping_langcache():
        from .langcache import stats
        s = stats(SETTINGS)
        discovered["langcache_hit_rate"] = float(s.get("hit_rate", 0.0))
        return {"detail": f"hit_rate {s.get('hit_rate', 0.0)}"}

    def ping_openai():
        # OpenAI embeddings are optional; treat a missing key as "down" (not an error).
        if not getattr(SETTINGS, "openai_api_key", ""):
            raise RuntimeError("OPENAI_API_KEY not set")
        return {"detail": "configured"}

    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout

    _probe_fns = {
        "pubmed": ping_pubmed,
        "arxiv": ping_arxiv,
        "biorxiv": ping_biorxiv,
        "openalex": ping_openalex,
        "chemrxiv": ping_chemrxiv,
        "medrxiv": ping_medrxiv,
        "redis": ping_redis,
        "redisvl": probe_redisvl,
        "streams": ping_streams,
        "agent_memory": ping_agent_memory,
        "langcache": ping_langcache,
        "openai": ping_openai,
        "anthropic": ping_anthropic,
        "consumer": ping_consumer,
    }
    # Probes run concurrently, but a single slow upstream (e.g. OpenAlex can take
    # ~13s) must not stall the whole response: the dev-ui aborts /status after 9s
    # and then renders the backend as offline. Bound the sweep to a budget well
    # under that; any probe still running at the deadline is reported down.
    _PROBE_BUDGET_S = 7.0
    _ex = ThreadPoolExecutor(max_workers=len(_probe_fns))
    try:
        _futs = {name: _ex.submit(_probe, fn) for name, fn in _probe_fns.items()}
        _deadline = time.monotonic() + _PROBE_BUDGET_S
        connections = {}
        for name, fut in _futs.items():
            try:
                connections[name] = fut.result(timeout=max(0.0, _deadline - time.monotonic()))
            except _FutureTimeout:
                connections[name] = {
                    "ok": False,
                    "detail": f"probe exceeded {_PROBE_BUDGET_S:.0f}s budget",
                }
    finally:
        _ex.shutdown(wait=False, cancel_futures=True)

    healthy = all(c["ok"] for c in connections.values())

    # Log any up/down flips to the service status CSV.
    from .monitoring import (
        last_new_paper_at,
        new_papers_last_hour,
        recent_status_flips,
        record_status,
        seconds_since_last_new_paper,
        seen_count,
        status_flip_counts,
    )
    record_status(connections)

    # Real profile size (the backend's "memory" is the local lab profile).
    try:
        from .memory import load_profile
        memory_records = len(load_profile().items)
    except Exception:
        memory_records = 0

    last_seen = last_new_paper_at()

    metrics = {
        "papers_processed_last_hour": 0,
        "papers_processed_total": 0,
        "langcache_hit_rate": discovered.get("langcache_hit_rate", 0.0),
        "new_papers_seen": seen_count(),
        "new_papers_last_hour": new_papers_last_hour(),
        "last_new_paper_at": last_seen,
        "seconds_since_last_new_paper": seconds_since_last_new_paper(),
        "status_flip_counts": status_flip_counts(),
        "status_flip_series": recent_status_flips(200),
        "alerts_fired_last_hour": 0,
        "corpus_index_docs": discovered.get("corpus_index_docs", 0),
        "stream_length": discovered.get("stream_length", 0),
        "stream_pending": 0,
        "memory_records": memory_records,
        "last_processed_at": last_seen,
        "consumer_last_heartbeat": _utc_now_iso(),
    }

    # Redis surfaces that are genuinely live right now.
    redis_sources: list[str] = []
    if connections["redis"]["ok"]:
        redis_sources.append("Digest store")
    if connections["redisvl"]["ok"]:
        redis_sources.append("RedisVL corpus index")

    return {
        "healthy": healthy,
        "connections": connections,
        "metrics": metrics,
        "redis_sources": redis_sources,
    }
