"""FastAPI app + all routes (SPEC §8).

Route surface (CORS open to the Vite dev origin, no auth):

    GET  /api/health            -> {"status": "ok"}
    GET  /status                -> dashboard health (see dev-ui/README.md)
    GET  /api/profile           -> Profile
    POST /api/search            -> list[SearchHit]   (<=5, live)
    GET  /api/digest/history    -> list[DigestSummary]
    GET  /api/digest/{date}     -> list[DigestEntry] (frozen)
    POST /api/profile/memory    -> Profile           (stretch)

Routes are thin: they validate, call into engine/memory/redis_client, and shape the
response. Handler bodies are stubs.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import status as status_probe
from .models import (
    DigestEntry,
    DigestSummary,
    MemoryWriteRequest,
    Profile,
    SearchHit,
    SearchRequest,
)

app = FastAPI(title="Baskr", version="0.0.1")

# TODO: tighten to the actual Vite dev origin(s) at build time.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    raise NotImplementedError


@app.post("/api/search", response_model=list[SearchHit])
def search(body: SearchRequest) -> list[SearchHit]:
    raise NotImplementedError


@app.get("/api/digest/history", response_model=list[DigestSummary])
def digest_history() -> list[DigestSummary]:
    raise NotImplementedError


@app.get("/api/digest/{date}", response_model=list[DigestEntry])
def digest_for_date(date: str) -> list[DigestEntry]:
    raise NotImplementedError


@app.post("/api/profile/memory", response_model=Profile)
def add_memory(body: MemoryWriteRequest) -> Profile:
    """Stretch: append a finding to the profile so memory visibly grows."""
    raise NotImplementedError
