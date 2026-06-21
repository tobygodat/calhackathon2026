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

app = FastAPI(title="Baskr", version="0.1.0")

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

def _probe(fn, *args, **kwargs) -> dict:
    t0 = time.monotonic()
    try:
        fn(*args, **kwargs)
        return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)}


@app.get("/status")
def system_status() -> dict:
    from .config import SETTINGS

    # Redis
    def ping_redis():
        import redis as _r
        c = _r.from_url(SETTINGS.redis_url, socket_timeout=1,
                        socket_connect_timeout=1, decode_responses=True)
        c.ping()

    # OpenAI
    def ping_openai():
        if not SETTINGS.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        from openai import OpenAI
        OpenAI(api_key=SETTINGS.openai_api_key).models.list()

    # Anthropic
    def ping_anthropic():
        if not SETTINGS.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic
        Anthropic(api_key=SETTINGS.anthropic_api_key).models.list()

    # PubMed
    def ping_pubmed():
        import requests
        r = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
            params={"retmode": "json"},
            timeout=5,
        )
        r.raise_for_status()

    # Run probes concurrently so total latency ~= the slowest probe, not the sum.
    from concurrent.futures import ThreadPoolExecutor

    _probe_fns = {
        "redis": ping_redis,
        "openai": ping_openai,
        "anthropic": ping_anthropic,
        "pubmed": ping_pubmed,
    }
    with ThreadPoolExecutor(max_workers=len(_probe_fns)) as _ex:
        _futs = {name: _ex.submit(_probe, fn) for name, fn in _probe_fns.items()}
        connections = {name: fut.result() for name, fut in _futs.items()}
    healthy = all(c["ok"] for c in connections.values())

    # Metrics from frozen digests
    total_papers = 0
    if _DIGEST_DIR.exists():
        for f in _DIGEST_DIR.glob("*.json"):
            try:
                total_papers += len(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass

    metrics = {
        "papers_processed_total": total_papers,
        "papers_processed_last_hour": 0,
        "alerts_fired_last_hour": 0,
        "corpus_index_docs": total_papers,
        "stream_length": 0,
        "stream_pending": 0,
        "memory_records": 7,
        **_pipeline_cache.get("metrics", {}),
    }

    return {
        "healthy": healthy,
        "connections": connections,
        "metrics": metrics,
        "redis_sources": ["pubmed", "arxiv", "biorxiv"],
    }


@app.post("/pipeline/search")
async def pipeline_search(body: dict) -> dict:
    global _pipeline_cache
    query = body.get("query", "gut microbiome")
    days = int(body.get("days", 7))
    sources = body.get("sources") or ["pubmed", "arxiv", "biorxiv"]
    max_results = int(body.get("max_results", 50))

    # Nature source is disabled per dev-ui warning
    safe_sources = [s for s in sources if s != "nature"]

    try:
        from system_pieces.data_pipeline import DataPipeline
        pipeline = DataPipeline(sources=safe_sources)
        result = pipeline.fetch(
            query,
            days=days,
            max_per_source=max(max_results // max(len(safe_sources), 1), 10),
        )
        papers_out = []
        for p in result.papers:
            d = p.to_dict()
            d.pop("raw", None)
            papers_out.append(d)

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
