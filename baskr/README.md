# Baskr

Research radar for a gut-microbiome lab. Holds a persistent **lab context profile**
in Redis agent memory, classifies new papers against it, and surfaces the ones that
matter — each with a one-sentence plain-language reason.

> Scaffold only. File structure and contracts are in place; function bodies are stubs
> (`raise NotImplementedError`). See [`../SPEC.md`](../SPEC.md) for the full product spec.

## Two surfaces, one engine

| Surface | Trigger | Purpose |
|---|---|---|
| **Active Search** | User submits an open question | Live query against recent papers |
| **Daily Digest** | Pre-generated / frozen | Relevant papers from the day's feed, no query |

Both call `engine.classify_paper()` and reason against the same profile.

## Layout

```
baskr/
├── backend/          # FastAPI app (§8 of SPEC)
│   └── app/          # config, models, redis, embeddings, llm, prompts,
│                     # memory, engine, ingest, seed_profile
├── frontend/         # React + Vite + TS + Tailwind (three panels)
├── data/             # profile_seed.json + frozen digests
└── scripts/          # offline digest generation
```

## Paper ingestion — reuses the existing pipeline

Baskr does **not** ship its own PubMed fetcher. Paper fetching is delegated to the
multi-source [`implementations/data_pipeline`](../implementations/data_pipeline)
package (`DataPipeline`), which already normalizes PubMed/arXiv/bioRxiv/Nature into
one `Paper` model with cross-source dedupe. `backend/app/ingest.py` and `engine.py`
import it directly; there is no `pubmed.py` here on purpose.

## Build order

`config` → `redis_client` + `embeddings` + `llm` → `prompts` + `memory` → `engine`
→ `main` → `ingest` / `seed_profile` / `freeze_digest` → frontend.

## Quickstart (once implemented)

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env        # fill in keys
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```
