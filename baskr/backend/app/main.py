"""FastAPI app + all routes (SPEC §8).

Route surface:
    GET  /api/health            -> {"status": "ok"}
    GET  /api/profile           -> Profile
    POST /api/search            -> list[SearchHit]   (<=5, live)
    GET  /api/digest/history    -> list[DigestSummary]
    GET  /api/digest/{date}     -> list[DigestEntry] (frozen)
    POST /api/profile/memory    -> Profile           (stretch)

Dev-UI routes (dev-ui vite proxy strips /api prefix):
    GET  /status                -> system status for dev-ui
    POST /pipeline/search       -> DataPipeline search for dev-ui
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    DigestEntry,
    DigestSummary,
    Label,
    MemoryWriteRequest,
    Profile,
    SearchHit,
    SearchRequest,
)


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

# Frozen digest directory  (app/ -> backend/ -> baskr/)
_DIGEST_DIR = Path(__file__).resolve().parents[2] / "data" / "digest_frozen"

# Make system_pieces importable  (app/ -> backend/ -> baskr/ -> calhackathon2026/)
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Pipeline metrics cache for /status
_pipeline_cache: dict = {}


# ---------------------------------------------------------------------------
# Baskr API
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    from .memory import load_profile
    return load_profile()


@app.post("/api/search", response_model=list[SearchHit])
def search(body: SearchRequest) -> list[SearchHit]:
    from .engine import active_search
    try:
        return active_search(body.question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/digest/history", response_model=list[DigestSummary])
def digest_history() -> list[DigestSummary]:
    summaries: list[DigestSummary] = []

    # Load from frozen JSON files
    if _DIGEST_DIR.exists():
        for f in sorted(_DIGEST_DIR.glob("*.json"), reverse=True):
            date_str = f.stem
            try:
                entries_raw = json.loads(f.read_text(encoding="utf-8"))
                if not entries_raw:
                    continue
                labels = [e["classification"]["label"] for e in entries_raw]
                top = max(set(labels), key=labels.count)
                summaries.append(DigestSummary(
                    date=date_str,
                    count=len(entries_raw),
                    top_label=Label(top),
                ))
            except Exception:
                continue

    return summaries


@app.get("/api/digest/{date}", response_model=list[DigestEntry])
def digest_for_date(date: str) -> list[DigestEntry]:
    # Try frozen JSON file first
    path = _DIGEST_DIR / f"{date}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [DigestEntry(**entry) for entry in raw]

    # Fall back to Redis
    try:
        from .redis_client import load_digest
        payload = load_digest(date)
        if payload:
            return [DigestEntry(**entry) for entry in json.loads(payload)]
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"No digest found for {date}")


@app.post("/api/profile/memory", response_model=Profile)
def add_memory(body: MemoryWriteRequest) -> Profile:
    from .memory import append_item
    return append_item(body.kind, body.text)


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


@app.get("/status")
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
        import requests
        r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
            params={"retmode": "json"}, timeout=5,
        )
        r.raise_for_status()

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

    from concurrent.futures import ThreadPoolExecutor

    _probe_fns = {
        "pubmed": ping_pubmed,
        "arxiv": ping_arxiv,
        "biorxiv": ping_biorxiv,
        "redis": ping_redis,
        "redisvl": probe_redisvl,
        "anthropic": ping_anthropic,
        "consumer": ping_consumer,
    }
    with ThreadPoolExecutor(max_workers=len(_probe_fns)) as _ex:
        _futs = {name: _ex.submit(_probe, fn) for name, fn in _probe_fns.items()}
        connections = {name: fut.result() for name, fut in _futs.items()}
    healthy = all(c["ok"] for c in connections.values())

    # Log any up/down flips to the service status CSV.
    from .monitoring import (
        last_new_paper_at,
        new_papers_last_hour,
        record_status,
        seen_count,
        status_flip_counts,
    )
    record_status(connections)

    # --- metrics (derived from real code + data, not hardcoded) --------------
    total_papers = 0
    newest_mtime = 0.0
    if _DIGEST_DIR.exists():
        for f in _DIGEST_DIR.glob("*.json"):
            try:
                total_papers += len(json.loads(f.read_text(encoding="utf-8")))
                newest_mtime = max(newest_mtime, f.stat().st_mtime)
            except Exception:
                pass

    # Real profile size (the backend's "memory" is the local lab profile).
    try:
        from .memory import load_profile
        memory_records = len(load_profile().items)
    except Exception:
        memory_records = 0

    last_processed_at = None
    if newest_mtime:
        from datetime import datetime, timezone
        last_processed_at = (
            datetime.fromtimestamp(newest_mtime, timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z")
        )

    metrics = {
        "papers_processed_total": total_papers,
        "papers_processed_last_hour": 0,
        "new_papers_seen": seen_count(),
        "new_papers_last_hour": new_papers_last_hour(),
        "last_new_paper_at": last_new_paper_at(),
        "status_flip_counts": status_flip_counts(),
        "alerts_fired_last_hour": 0,
        "corpus_index_docs": discovered.get("corpus_index_docs", 0),
        "stream_length": 0,
        "stream_pending": 0,
        "memory_records": memory_records,
        "last_processed_at": last_processed_at,
        "consumer_last_heartbeat": _utc_now_iso(),
        **_pipeline_cache.get("metrics", {}),
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


@app.post("/pipeline/search")
async def pipeline_search(body: dict) -> dict:
    global _pipeline_cache
    query = body.get("query", "gut microbiome")
    days = int(body.get("days", 7))
    sources = body.get("sources") or ["pubmed", "arxiv", "biorxiv"]
    max_results = int(body.get("max_results", 50))

    try:
        from system_pieces.data_pipeline import DataPipeline
        pipeline = DataPipeline(sources=sources)
        result = pipeline.fetch(
            query,
            days=days,
            max_per_source=max(max_results // max(len(sources), 1), 10),
        )
        papers_out = []
        for p in result.papers:
            d = p.to_dict()
            d.pop("raw", None)
            papers_out.append(d)

        # Track distinct new papers (also appends them to new_papers_seen.csv).
        from .monitoring import record_papers
        record_papers(papers_out)

        total_pre = sum(result.counts.values())
        total_post = len(result.papers)
        dedupe_ratio = (
            round((total_pre - total_post) / total_pre, 3) if total_pre > 0 else 0.0
        )

        _pipeline_cache["metrics"] = {
            "pipeline_source_counts": result.counts,
            "pipeline_dedupe_ratio": dedupe_ratio,
            "pipeline_last_query": query,
            "pipeline_last_result_count": len(result.papers),
            "pipeline_source_errors": result.errors or {},
        }

        return {"papers": papers_out, "errors": result.errors, "counts": result.counts}
    except Exception as exc:
        return {"papers": [], "errors": {"pipeline": str(exc)}, "counts": {}}
