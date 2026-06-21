"""FastAPI surface for the Context Initialization Engine.

Endpoints:
- ``POST /upload``  multipart PDF -> extract + store, returns the items + counts.
- ``GET  /search``  free-text query -> top matching context items (the search
                    incoming data performs against the user context).
- ``GET  /context`` list the accumulated user context (optionally one kind).
- ``DELETE /context`` clear the store.
- ``GET  /health``  backend/key status.

Run with:  uvicorn context_engine.api:app --reload --port 8100
"""

from __future__ import annotations

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile

from .config import SETTINGS
from .engine import ContextEngine
from .extractor import using_real_model
from .models import ItemKind

app = FastAPI(title="Context Initialization Engine", version="0.1.0")
_engine = ContextEngine(SETTINGS)


def _parse_kind(kind: str | None) -> ItemKind | None:
    if not kind:
        return None
    try:
        return ItemKind(kind)
    except ValueError:
        raise HTTPException(400, f"kind must be one of {[k.value for k in ItemKind]}")


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "extraction": "claude" if using_real_model(SETTINGS) else "heuristic",
        "embeddings": "openai" if SETTINGS.openai_api_key else "keyless",
        "store": type(_engine.store).__name__,
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")
    try:
        result = _engine.ingest_pdf(data, title=file.filename or "")
    except RuntimeError as exc:
        raise HTTPException(422, str(exc))
    return {
        "source_id": result.source_id,
        "source_title": result.source_title,
        "num_chunks": result.num_chunks,
        "used_real_model": result.used_real_model,
        "counts": result.counts(),
        "items": [it.to_dict() for it in result.items],
    }


@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(None, ge=1, le=50),
    kind: str | None = Query(None),
) -> dict:
    hits = _engine.search(q, top_k=top_k, kind=_parse_kind(kind))
    return {"query": q, "hits": [h.to_dict() for h in hits]}


@app.post("/accept")
def accept(
    text: str = Body(..., embed=True),
    kind: str = Body("finding", embed=True),
    source_title: str = Body("review", embed=True),
    auto_apply: bool = Body(True, embed=True),
) -> dict:
    """Accept an incoming claim; revise the context in proportion to it.

    Set ``auto_apply=false`` to preview the proposed revision without mutating.
    """
    parsed = _parse_kind(kind) or ItemKind.FINDING
    proposal = _engine.accept(
        text, kind=parsed, source_title=source_title, auto_apply=auto_apply
    )
    return proposal.to_dict()


@app.get("/context")
def context(kind: str | None = Query(None)) -> dict:
    items = _engine.context(kind=_parse_kind(kind))
    return {"count": len(items), "items": [it.to_dict() for it in items]}


@app.delete("/context")
def clear() -> dict:
    _engine.clear()
    return {"ok": True}
