# Context Initialization Engine

Turns a user's research PDFs — prior work, planning/scaffolding for a new paper,
or in-progress drafts — into a **vector-searchable user context** that **evolves
and changes its mind** as new evidence arrives. Incoming data is searched against
this context; accepted contradictions revise it in proportion to how much they
overturn it.

Each PDF is distilled into three kinds of items:

| Kind | Definition |
|------|------------|
| **finding** | A conclusion the paper makes as its point (a result it stands behind). |
| **question** | An unknown the paper raises — open problem, unresolved limitation, or planned future experiment/research. |
| **assumption** | A fact the paper takes as true to make its argument but does **not** verify within the publication. |

## How it works

```
PDF bytes ──▶ pdf.py ──▶ chunk ──▶ extractor.py ──▶ embeddings.py ──▶ store.py
            extract text          findings/         1536-dim         vector
                                  questions/        vectors          index
                                  assumptions
```

Every stage **degrades gracefully** so the engine runs with zero setup:

| Stage | Real backend | Keyless fallback |
|-------|--------------|------------------|
| Extraction | Claude (`EXTRACT_MODEL`, forced tool-use JSON) | sentence-level cue-phrase heuristic |
| Embeddings | OpenAI `text-embedding-3-small` (1536-d) | hashed bag-of-tokens (1536-d) |
| Store | Redis Query Engine (HNSW) **or** Iris Redis Agent Memory | local numpy file |

The embedders are interchangeable at rest, and all stores share one interface,
so you can add keys/infra incrementally without reindexing logic changes.

## Belief revision — context that changes its mind

The novel part. Most memory systems only *accumulate*. This one **revises** when
the user accepts an incoming claim that contradicts an existing belief, by an
amount proportional to how much the claim overturns it:

```
accept(claim) ─▶ locate the belief it's about   (vector search → relatedness)
              ─▶ judge how much it overturns it  (Claude → severity 0..1)
              ─▶ apply by severity:
                   < 0.30   merge      revise in place (same id, version++)
                   0.30–0.70 fork      keep both; old belief marked "contested"
                   >= 0.70  supersede  retire old belief (kept as history); install new
```

> "The Earth is *slightly egg-shaped*" → **merge** (small nuance, belief stays).
> "The Earth is *actually square*" → **supersede** (core overturned, belief replaced).

Relatedness (embedding cosine) only finds *which* belief is under attack —
embeddings measure aboutness, not agreement. Severity (the magnitude) comes from
the LLM judge. Superseded beliefs are retained as history with a `supersedes`
link and a provenance log, so you can see *how* a belief evolved.

## The three store tiers (and what they symbolize)

A single accepted contradiction traverses Redis's own evolution:

| Tier | Redis primitive | Role here |
|---|---|---|
| Working memory | Redis core | recent uploads / interactions |
| Locate + score | Query Engine / RedisVL vectors | find the belief under attack, with a cosine |
| Evolving beliefs | **Iris Redis Agent Memory** | durable, revisable belief store + provenance |

Set `CONTEXT_STORE=iris` (with `AGENT_MEMORY_*` creds) to use the Iris belief
tier; `redis` for the Query Engine vector index; `local` (default) for a
zero-infra numpy store. Each falls back to `local` if unavailable.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # optional: add ANTHROPIC_API_KEY / OPENAI_API_KEY
```

With no `.env`, you get heuristic extraction + keyless embeddings + a local
store — fully functional, lower quality.

## Use

CLI:

```bash
python -m context_engine.cli ingest paper1.pdf paper2.pdf
python -m context_engine.cli search "does gut microbiota affect mood?"
python -m context_engine.cli accept "The effect actually reverses at high doses." --kind finding
python -m context_engine.cli accept "..." --preview      # assess without mutating
python -m context_engine.cli context --kind question
python -m context_engine.cli clear
```

HTTP API:

```bash
uvicorn context_engine.api:app --reload --port 8100
# POST   /upload    multipart PDF -> extracted items + counts
# GET    /search?q=...&kind=question&top_k=8
# POST   /accept    {text, kind, auto_apply} -> belief-revision proposal (+ applies)
# GET    /context?kind=finding
# DELETE /context
# GET    /health    backend + key status
```

Programmatic:

```python
from context_engine.engine import ContextEngine
eng = ContextEngine()
result = eng.ingest_pdf(open("paper.pdf", "rb").read(), title="paper.pdf")
hits = eng.search("short-chain fatty acids from fiber")
```

## Tests

```bash
python -m pytest tests/ -q     # keyless/local path, no keys or infra needed
```

## Layout

```
context_engine/
  config.py       Settings + .env loading (only place that reads os.environ)
  models.py       ContextItem / ItemKind / ExtractionResult contracts
  pdf.py          PDF text extraction (pypdf) + overlapping chunking
  extractor.py    Claude forced-tool-use extraction + heuristic fallback
  embeddings.py   OpenAI + keyless embedders (both 1536-d, L2-normalized)
  store.py        LocalStore (numpy) + RedisStore (HNSW) + IrisStore (RAM), one interface
  revision.py     belief revision: assess() + apply() (merge / fork / supersede)
  engine.py       orchestration: ingest_pdf() + search() + accept()
  api.py          FastAPI surface
  cli.py          terminal interface
```
