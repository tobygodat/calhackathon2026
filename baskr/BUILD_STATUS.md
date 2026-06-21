# Baskr Build Status
Updated: 2026-06-21T05:00:00Z   State: IN_PROGRESS

| Phase | Name                          | Status | Checks passing | Notes |
|-------|-------------------------------|--------|----------------|-------|
| 0     | Foundations & boot            | DONE   | 4/4            | verified by director |
| 1     | Redis architecture            | DONE   | 5/5            | live redis; RedisVL+brute-force fallback |
| 2     | Embeddings · LLM · prompts    | DONE   | 4/4            | tool-use JSON; deterministic keyless fallbacks |
| 3     | Engine · ingest · seed        | DONE   | 3/3            | 5-step engine, staged fallback, seed 8 items |
| 4     | API surface                   | DONE   | 4/4            | all routes implemented; 59 tests green |
| 5     | Dev UI comprehensive view     | NEXT   | 0/3            | |
| 6     | Agent loop & streaming        | TODO   | 0/3            | |

## Environment (iteration 1 probe)
- Python 3.11.15 · node 22.22 · npm 10.9 · local redis-server + redis-cli present.
- OPENAI_API_KEY / ANTHROPIC_API_KEY / NCBI_API_KEY / REDIS_URL all UNSET.
  → OpenAI + Anthropic run in DEGRADED (deterministic fake) mode.
  → Redis runs LIVE against redis://localhost:6379 (start local redis-server).

## Working (verified live)
- FastAPI boots keyless: `GET /api/health` → {"status":"ok"}.
- `GET /status` returns the exact dev-ui contract; per-feature Redis probes are REAL.
- Import break fixed (system_pieces path shim).
- Redis layer LIVE: redis_client (ensure_papers_index idempotent, upsert_paper,
  query_similar nearest-neighbor, store/load_digest); memory (load/retrieve/append
  in lab:{lab_id}); streams (XADD/XLEN); langcache (Redis-backed, hit-rate).
- Embeddings: embed_text/embed_batch → 1536-dim L2-normalized (deterministic keyless).
- LLM: classify() → schema-valid Classification; asymmetric-recall degraded classifier
  produces real ANSWERS/CONTRADICTS/EXTENDS labels for relevant gut-microbiome papers.
- Engine: classify_paper 5-step flow; active_search (fetch+classify+filter+sort+cap);
  run_digest (batch classify, return non-NOT_RELEVANT hits).
- Ingest: fetch_recent (DataPipeline with 8s timeout → staged fallback); ingest (embed+upsert).
- seed_profile: loads data/profile_seed.json (8 real gut-microbiome items) into Redis.
- Frozen digests: 3 days pre-generated (data/digest_frozen/{date}.json + Redis).
- API routes: GET /api/profile, POST /api/search, GET /api/digest/history,
  GET /api/digest/{date}, POST /api/profile/memory, POST /api/pipeline/search.
- Pipeline metrics surfaced in /status via pipeline_state module.
- Tests: 59 pass (+11 API tests Phase 4, +3 seed live tests, +5 redis-integration live).

## Not working / blocked
- No RediSearch module on local redis → vector search runs brute-force fallback.
- openai/anthropic keys absent → deterministic degraded mode.
- External source egress (PubMed/arXiv/bioRxiv) → staged fallback fires automatically.
- Consumer (Phase 6) not yet running.
- Dev UI Phase 5 panels not yet built.

## Decisions logged this run
- See claude-chats-hack/ARCHITECTURE_DECISIONS.md (entries 1–8).
