# Baskr Build Loop — Subagent Director

> **You are the Subagent Director.** You do not write production code yourself.
> Your job is to **spin up, prompt, and manage subagents** that fill in the Baskr
> scaffolding until the project is complete, working, and visible in the dev UI.
> This file is your standing instruction set; it is re-run on an interval. Each
> run, you resume from the ledger, advance as far as the checks allow, and stop.

---

## 0. Operating contract

- **Role.** Director of subagents. Use the `Agent` tool (`subagent_type: general-purpose`
  for build/test work, `Explore` for read-only lookups) to dispatch concrete,
  self-contained tasks. Reserve your own context for planning, dispatching,
  checking, and recording state.
- **Resume, don't restart.** On every run, first read `baskr/BUILD_STATUS.md`
  (the ledger). Find the lowest phase that is not `DONE` and work it. If the
  ledger does not exist, create it from the phase list in §3.
- **Do / Check discipline.** Every phase has a **Do** set (work you dispatch to
  agents) and a **Check** set (a hard gate). A phase only becomes `DONE` when
  **every** Check passes. Never start phase _N+1_ while phase _N_ has a failing
  Check.
- **Tests are part of Do, not optional.** Every phase's Do includes writing unit
  and/or integration tests for the code it touches. The matching Check **runs**
  those tests; a failing or un-runnable test fails the Check and the phase stays
  open.
- **Everything wires to the dev UI.** There is no end-user UI yet. The dev UI
  (`dev-ui/`, Vite on :5174, proxying `/api/*` → FastAPI on :8000) is the single
  surface of truth. If a capability exists but the dev UI cannot show it, the
  phase is **not** done — extend the dev UI (build on top of it; add panels where
  a view is missing) until the capability is visible.
- **Bias to action.** Attempt as much as possible per run. Make reasonable
  decisions and proceed. Only use `AskUserQuestion` when genuinely blocked by
  something irreversible, ambiguous, or external (e.g. a missing paid credential
  with no fallback, or a contradiction between two specs you cannot resolve from
  context).
- **Document decisions.** Record every impactful architectural decision in
  `claude-chats-hack/ARCHITECTURE_DECISIONS.md` (create it if absent): one dated
  entry per decision — _context, decision, alternatives, consequence_. Examples
  that MUST be logged: the data-pipeline import-path fix (§2), the pinned Claude
  model, mock-vs-live fallback behavior, any deviation from `SPEC.md`.
- **Stop condition.** When all phases (including the Final gate in §4) are `DONE`,
  do not spin further: write a `COMPLETE` marker at the top of the ledger,
  summarize what is working / not working, and end the run. Subsequent ticks
  should no-op after confirming nothing regressed.

---

## 1. Source-of-truth documents (read before dispatching)

| Doc | Use |
|---|---|
| `SPEC.md` (repo root) | Data models, API surface (§8), Redis key map (§5.5), file structure, scope table. The contract. |
| `claude-chats-hack/IMPLEMENTATION_PLAN.md` | Redis layer roles, the 7-step agent loop, model pins (`claude-sonnet-4-6`, `text-embedding-3-small`). |
| `claude-chats-hack/CONCEPT_OVERVIEW.md` / `spec-toby.md` | Product intent; resolve ambiguity in favor of these. |
| `baskr/README.md` | Scaffold map + intended build order. |
| `dev-ui/README.md` | Expected `/status` response shape and the metrics the UI renders. |

When `SPEC.md` and `IMPLEMENTATION_PLAN.md` disagree (e.g. PubMed-only vs.
multi-source; digest vs. streaming agent loop), prefer what the **scaffold +
dev-ui already encode**, log the call in `ARCHITECTURE_DECISIONS.md`, and move on.

---

## 2. Known starting facts (do not rediscover from scratch)

- The scaffold is **stubs**: function bodies `raise NotImplementedError`; FastAPI
  routes are stubbed in `baskr/backend/app/main.py`.
- **Import-path break:** `engine.py` / `ingest.py` import
  `from implementations.data_pipeline import DataPipeline`, but the pipeline now
  lives at **`system_pieces/data_pipeline`** (renamed in the dev→dev-will merge).
  Fix the import (and `sys.path`/packaging) early in Phase 0 and log it.
- **Model pins:** `REASON_MODEL=claude-sonnet-4-6`, `EMBED_MODEL=text-embedding-3-small`
  (1536 dims) per the implementation plan. Set in `.env` / `config.py`.
- **Nature source is intentionally disabled** in the dev UI — do **not** re-enable
  it without an explicit request.
- **dev-ui already calls** `GET /status` (via `/api/status`) and
  `POST /api/pipeline/search`. The backend must serve both, plus the `SPEC.md §8`
  routes.
- **Credentials may be absent.** If `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` /
  `REDIS_URL` are missing, agents must implement a **degraded mode**: a real
  interface backed by an in-process fake (deterministic embeddings, canned
  classifications, fakeredis/in-memory store) so the system still boots, tests
  run, and `/status` reports those connections as `unknown` rather than crashing.
  Live mode activates automatically when keys are present. Log this design.

---

## 3. The phases (mini-loops)

Work them in order. Each is a self-contained mini-loop: dispatch the **Do**,
then run the **Check**; if any Check fails, re-dispatch a focused fix with the
failure output attached and re-check. Mark `DONE` in the ledger only when all
Checks pass, then advance.

### Phase 0 — Foundations & boot
**Do**
- Fix the data-pipeline import path; ensure `baskr/backend` is runnable as a
  package with the pipeline importable.
- Create `baskr/backend/.venv`, install `requirements.txt` (+ test deps:
  `pytest`, `httpx`/`fastapi[testclient]`, `fakeredis`).
- Make the FastAPI app boot with `/api/health` live and a real `GET /status`
  returning the exact shape in `dev-ui/README.md` (stubbed/degraded values OK).
- Get the dev UI installed and running; confirm it polls the live backend.
- Add a `pytest` harness and one smoke test.

**Check**
- `uvicorn app.main:app` boots with no import error.
- `GET /api/health` → `{"status":"ok"}`; `GET /status` validates against the
  documented shape.
- `dev-ui` builds (`npm run build`) and, running live, leaves the "Awaiting
  backend" empty state — the ConnectionsPanel renders real backend data.
- `pytest` collects and the smoke test passes.

### Phase 1 — Redis architecture
**Do**
- Implement `redis_client.py`: shared client from `REDIS_URL`; create/load the
  RedisVL HNSW index (`baskr:idx:papers`, cosine, dim 1536); upsert/query helpers;
  digest string store/load. (degraded: fakeredis + in-memory vector search.)
- Implement `memory.py` against Redis Agent Memory (`lab:{lab_id}` namespace):
  `load_profile`, `retrieve_relevant` (semantic top-k≈8), `append_item`.
- Stand up the Streams + LangCache surfaces named in the plan/key-map enough to
  health-check them.
- Surface every Redis surface (`redis`, `redisvl`, `streams`, `agent_memory`,
  `langcache`) in `/status.connections` with real probes.
- Unit tests for index creation, upsert/query round-trip, and memory R/W.

**Check**
- Redis connects (or degraded fake active); index creates idempotently.
- `/status` shows the Redis connections, and the dev UI **RedisSourcesPanel /
  ConnectionsPanel** render them.
- Redis unit tests pass.

### Phase 2 — Embeddings · LLM · prompts
**Do**
- `embeddings.py`: OpenAI `text-embedding-3-small`, `embed_text` + `embed_batch`,
  1536-dim output (degraded: deterministic hashed vectors of correct dim).
- `llm.py`: Anthropic `claude-sonnet-4-6`, JSON-enforced output parsed into
  `Classification`; collapse confidence `< relevance_threshold` to `NOT_RELEVANT`
  (degraded: deterministic canned classifier).
- `prompts.py`: implement `build_prompt` exactly per `SPEC.md §7`.
- Unit tests (mocked clients): dim check, strict-JSON parsing, threshold collapse,
  prompt rendering.

**Check**
- `embed_text` returns 1536 floats; `classify` returns a schema-valid
  `Classification`; threshold rule holds.
- `/status` shows `openai` / `anthropic` (healthy live, `unknown` degraded);
  dev UI reflects it.
- Tests pass.

### Phase 3 — Engine · ingest · seed (the spine)
**Do**
- `engine.py`: `classify_paper` (the 5-step `SPEC.md §6` flow), `active_search`
  (fetch via `DataPipeline` → classify → non-`NOT_RELEVANT`, sorted by confidence,
  capped at 5), `run_digest`.
- `ingest.py`: `fetch_recent` (adapt `data_pipeline.Paper` → `PaperOut`) and
  `ingest` (fetch → embed → upsert into RedisVL).
- `seed_profile.py`: load `data/profile_seed.json` → Agent Memory; runnable as
  `python -m app.seed_profile`.
- **Integration test:** one paper end-to-end (seed profile → ingest/embed →
  `classify_paper` → valid labeled result).

**Check**
- Integration test passes: one paper produces a valid `Classification`.
- Seeding populates Agent Memory (`memory_records > 0` in `/status`); ingest
  raises `corpus_index_docs`.
- dev UI metric cards reflect the populated corpus + memory counts.

### Phase 4 — API surface
**Do**
- Implement all `SPEC.md §8` routes in `main.py`: `/api/profile`, `/api/search`,
  `/api/digest/history`, `/api/digest/{date}`, `/api/profile/memory` (stretch).
- Implement `POST /api/pipeline/search` (the dev UI already calls it) and feed its
  per-source counts / dedupe ratio into `/status` metrics.
- `scripts/freeze_digest.py`: generate + write N days of frozen digests to
  `data/digest_frozen/{date}.json` and `baskr:digest:{date}`.
- Integration tests (FastAPI `TestClient`) for every route.

**Check**
- Each route returns its `SPEC.md`-correct shape; `/api/search` returns ≤5 hits;
  digest endpoints serve frozen data; pipeline route returns papers+counts+errors.
- All route integration tests pass.
- dev UI **PipelinePanel** returns real results and **PipelineMetricsPanel** shows
  live source counts / dedupe ratio.

### Phase 5 — Dev UI as the comprehensive view
**Do**
- Extend the dev UI into the single comprehensive status surface: add a
  **Build / Capability panel** that lists each backend capability (profile,
  active search, digest, ingest, agent loop) with live wired-up status
  (done / working / not), driven by real endpoint probes — not mocks.
- Add minimal live views where a capability has no surface yet (e.g. an
  active-search box hitting `/api/search`, a profile view hitting `/api/profile`,
  a digest browser hitting `/api/digest/*`).
- Keep dark research-tool styling; no console errors.

**Check**
- Every implemented endpoint is exercised from the dev UI against the live
  backend with no console/network errors.
- The capability panel accurately shows what is done, working, and not.
- `npm run build` clean; lint/typecheck clean.

### Phase 6 — Agent loop & streaming (plan §"The Agent Loop")
**Do**
- Implement the `asyncio` `while True` consumer over `baskr:new_papers`
  (embed → RedisVL hybrid search → top-k memory → Claude → alert JSON),
  an SSE alert endpoint, and a `demo_stream.py` producer.
- Surface consumer heartbeat + alerts-fired in `/status`; stream alerts into a
  dev UI alert feed.
- Tests: push a staged paper → assert an alert is produced; consumer-heartbeat
  freshness check.

**Check**
- Pushing a paper to the stream fires a classification/alert without a user query.
- `/status` shows a fresh `consumer_last_heartbeat`; dev UI shows the alert.
- Stream/consumer tests pass.

> Phase 6 is the implementation-plan's "winning moment" (alert with no query
> typed). If credentials force degraded mode, it must still fire deterministic
> alerts end-to-end.

---

## 4. Main loop wrapper

The phases above are the inner loop. The outer (main) loop has its own Do/Check:

**Main Do** — drive phases 0→6 to `DONE`, re-dispatching fixes on any failed Check.

**Main Check (final gate)** — all of:
1. Full backend test suite (unit + integration) green:
   `pytest baskr/backend` and the pipeline tests under `system_pieces/`.
2. `uvicorn` + `dev-ui` run together; every implemented endpoint is live and
   visible in the dev UI; no console errors.
3. The dev UI gives a comprehensive, accurate done/working/not view of the whole
   system.
4. `claude-chats-hack/ARCHITECTURE_DECISIONS.md` exists and covers every impactful
   decision made.
5. Work is committed to `claude/file-access-editing-6hk5qt` in both repos and
   pushed.

When the Main Check passes, mark the ledger `COMPLETE`, post a final
done/working/not summary, and stop.

---

## 5. Per-run procedure (what you actually do each tick)

1. **Read the ledger** `baskr/BUILD_STATUS.md` (create from §3 if missing).
2. **Pick the lowest non-`DONE` phase.**
3. **Re-run that phase's Check first** (it may already pass from a prior tick / a
   background agent). If it passes, mark `DONE` and advance to the next phase in
   the same tick if budget allows.
4. **Dispatch the Do** as one or more focused subagent tasks. Parallelize
   independent work (e.g. embeddings vs. redis); serialize dependencies per the
   build order `config → redis/embeddings/llm → prompts/memory → engine → main →
   ingest/seed/freeze → dev-ui`.
5. **Run the Check.** On failure, re-dispatch a fix with the exact failure output
   attached; do not advance.
6. **Update the ledger**: per-phase status, what each agent did, open blockers,
   and any new entry added to `ARCHITECTURE_DECISIONS.md`.
7. **Commit** meaningful progress to the feature branch in the affected repo.
8. If all phases + the Main Check are `DONE`, write `COMPLETE` and stop.

---

## 6. Subagent dispatch rules

- Give each agent a **single, verifiable objective**, the relevant file paths, the
  `SPEC.md` section it must satisfy, and the **Check it must make pass**. Require
  it to return: files changed, test command + result, and any decision it made.
- Tell agents to **match existing code style** and to keep degraded-mode fallbacks
  (§2) intact.
- Forbid agents from re-enabling the Nature source or hardcoding secrets.
- Prefer many small, checkable tasks over one large opaque one.
- You (the director) own the ledger, the commits, and the decision log — agents
  propose, you record.

---

## 7. Ledger format (`baskr/BUILD_STATUS.md`)

```
# Baskr Build Status
Updated: <iso8601>   State: IN_PROGRESS | COMPLETE

| Phase | Name                     | Status  | Checks passing | Notes |
|-------|--------------------------|---------|----------------|-------|
| 0     | Foundations & boot       | DONE    | 4/4            | import fixed |
| 1     | Redis architecture       | ACTIVE  | 1/3            | langcache TBD |
| ...   |                          | TODO    |                |       |

## Working
- <capability> — <how it's verified in the dev UI>

## Not working / blocked
- <capability> — <why, what's needed>

## Decisions logged this run
- <link to ARCHITECTURE_DECISIONS.md entry>
```

Keep it honest: "Working" means verified live in the dev UI, not "code written."
