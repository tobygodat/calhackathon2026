# Baskr Build Status
Updated: 2026-06-21T03:25:00Z   State: IN_PROGRESS

| Phase | Name                          | Status | Checks passing | Notes |
|-------|-------------------------------|--------|----------------|-------|
| 0     | Foundations & boot            | DONE   | 4/4            | verified by director |
| 1     | Redis architecture            | DONE   | 5/5            | live redis; RedisVL+brute-force fallback |
| 2     | Embeddings · LLM · prompts    | DONE   | 4/4            | tool-use JSON; deterministic keyless fallbacks |
| 3     | Engine · ingest · seed        | NEXT   | 0/3            | paused for review |
| 4     | API surface                   | TODO   | 0/4            | |
| 5     | Dev UI comprehensive view     | TODO   | 0/3            | |
| 6     | Agent loop & streaming        | TODO   | 0/3            | |

## Environment (iteration 1 probe)
- Python 3.11.15 · node 22.22 · npm 10.9 · local redis-server + redis-cli present.
- OPENAI_API_KEY / ANTHROPIC_API_KEY / NCBI_API_KEY / REDIS_URL all UNSET.
  → OpenAI + Anthropic run in DEGRADED (deterministic fake) mode.
  → Redis runs LIVE against redis://localhost:6379 (start local redis-server).

## Working (verified live by director)
- FastAPI boots keyless: `GET /api/health` → {"status":"ok"}.
- `GET /status` returns the exact dev-ui contract; per-feature Redis probes are REAL.
- Import break fixed (system_pieces path shim).
- Redis layer LIVE: redis_client (ensure_papers_index idempotent, upsert_paper,
  query_similar nearest-neighbor, store/load_digest); memory (load/retrieve/append
  in lab:{lab_id}); streams (XADD/XLEN); langcache (Redis-backed, hit-rate).
- `/status` shows redis/redisvl/streams/agent_memory/langcache ok:true with real
  details; metrics corpus_index_docs/memory_records/stream_length from live reads.
- Tests: 18 pass (4 Phase-0 smoke, 9 redis-unit/fakeredis, 5 redis-integration/live).
- Embeddings: embed_text/embed_batch → 1536-dim L2-normalized (OpenAI live, deterministic
  hashed fallback keyless). LLM: classify() → schema-valid Classification (Anthropic
  forced-tool-use JSON live, rule-based fallback keyless); sub-threshold→NOT_RELEVANT
  collapse centralized in _apply_threshold for both paths. prompts.build_prompt = exact
  SPEC §7. memory.retrieve_relevant now semantic-cosine (lexical fallback).
- REASON_MODEL pinned to claude-sonnet-4-6 (config + .env.example).
- Tests now 39 pass (+21: prompts, embeddings, llm, memory-semantic).

## Not working / blocked
- No RediSearch module on local redis (Docker layer egress 403-blocked) → vector
  search runs the brute-force fallback; RedisVL/HNSW path auto-engages under
  redis-stack. For demo: run redis/redis-stack-server.
- `retrieve_relevant` uses a lexical (Jaccard) ranker until embeddings (Phase 2).
- openai/anthropic metrics still degraded stubs until Phase 2/3.
- Backend route bodies (profile/search/digest) still NotImplementedError (Phase 4).

## Decisions logged this run
- See claude-chats-hack/ARCHITECTURE_DECISIONS.md (entries 1–7).
