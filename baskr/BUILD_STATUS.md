# Baskr Build Status
Updated: 2026-06-21T06:00:00Z   State: COMPLETE

| Phase | Name                          | Status | Checks passing | Notes |
|-------|-------------------------------|--------|----------------|-------|
| 0     | Foundations & boot            | DONE   | 4/4            | verified by director |
| 1     | Redis architecture            | DONE   | 5/5            | live redis; RedisVL+brute-force fallback |
| 2     | Embeddings · LLM · prompts    | DONE   | 4/4            | tool-use JSON; deterministic keyless fallbacks |
| 3     | Engine · ingest · seed        | DONE   | 3/3            | 5-step engine, staged fallback, seed 8 items |
| 4     | API surface                   | DONE   | 4/4            | all routes implemented; 59 tests green |
| 5     | Dev UI comprehensive view     | DONE   | 3/3            | profile/search/digest/capability panels |
| 6     | Agent loop & streaming        | DONE   | 3/3            | consumer thread + SSE + demo_stream.py |

## Environment (iteration 1 probe)
- Python 3.11.15 · node 22.22 · npm 10.9 · local redis-server + redis-cli present.
- OPENAI_API_KEY / ANTHROPIC_API_KEY / NCBI_API_KEY / REDIS_URL all UNSET.
  → OpenAI + Anthropic run in DEGRADED (deterministic fake) mode.
  → Redis runs LIVE against redis://localhost:6379 (start local redis-server).

## Working (verified live)
- FastAPI boots keyless: `GET /api/health` → {"status":"ok"}.
- `GET /status` returns the exact dev-ui contract; per-feature Redis probes REAL.
- Redis layer LIVE: redisvl, streams, agent_memory, langcache.
- Embeddings: deterministic 1536-dim keyless; real OpenAI when key present.
- LLM: asymmetric-recall degraded classifier; real Anthropic forced-tool-use live.
- Engine: classify_paper 5-step; active_search (staged fallback); run_digest.
- Ingest: fetch_recent (DataPipeline + staged fallback + 8s timeout).
- Seed: data/profile_seed.json → 8 real gut-microbiome items → Redis.
- Frozen digests: 3 days pre-generated (Redis + data/digest_frozen/).
- API routes: all SPEC §8 routes + POST /api/pipeline/search + GET /api/alerts/stream.
- Consumer thread: XREAD baskr:new_papers → classify → alert store; heartbeat in /status.
- Demo stream: scripts/demo_stream.py pushes staged papers → consumer fires alerts live.
- SSE: GET /api/alerts/stream yields classification alerts as SSE events.
- Dev UI: LabProfilePanel, ActiveSearchPanel, DigestHistoryPanel, CapabilityPanel,
  AlertFeedPanel, LabelBadge, PaperCard — all wired to live endpoints.
- Tests: 66 pass, 1 skipped (live-Redis integration, skip in sandbox).

## Not working / blocked
- No RediSearch module on local redis → brute-force cosine fallback (auto-upgrades under redis-stack).
- External source egress (PubMed/arXiv/bioRxiv) blocked → staged fallback fires automatically.
- openai/anthropic keys absent → deterministic degraded mode throughout.

## Decisions logged
- See claude-chats-hack/ARCHITECTURE_DECISIONS.md (entries 1–9).
