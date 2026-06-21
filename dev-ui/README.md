# Baskr Dev UI

Simple monitoring dashboard for pipeline health, Redis integrations, and external API connections.

## Run

```bash
cd dev-ui
npm install
npm run dev
```

Open http://localhost:5174

## Backend integration

When the FastAPI backend exposes `GET /status`, the UI polls it automatically via the Vite proxy (`/api/status` → `http://localhost:8000/status`).

Response shape (as emitted by `app/main.py:system_status`). Every service is
probed live and concurrently; `redis_sources` lists only the Redis surfaces that
are genuinely reachable at request time, and the metrics are derived from the
real frozen-digest data and lab profile — nothing is hardcoded.

```json
{
  "healthy": false,
  "connections": {
    "pubmed": { "ok": true, "latency_ms": 412.0 },
    "arxiv": { "ok": true, "latency_ms": 188.7 },
    "biorxiv": { "ok": true, "latency_ms": 233.1 },
    "redis": { "ok": false, "detail": "Timeout connecting to server" },
    "redisvl": { "ok": false, "detail": "Query Engine (search module) not loaded" },
    "anthropic": { "ok": true, "latency_ms": 540.2, "detail": "claude-sonnet-4-6" },
    "consumer": { "ok": true, "latency_ms": 0.0, "detail": "FastAPI online" }
  },
  "metrics": {
    "papers_processed_total": 8,
    "papers_processed_last_hour": 0,
    "new_papers_seen": 12,
    "alerts_fired_last_hour": 0,
    "corpus_index_docs": 0,
    "stream_length": 0,
    "stream_pending": 0,
    "memory_records": 7,
    "last_processed_at": "2026-06-21T08:02:58Z",
    "consumer_last_heartbeat": "2026-06-21T08:24:24Z"
  },
  "redis_sources": []
}
```

After a pipeline search the backend also merges these keys into `metrics`:
`pipeline_source_counts`, `pipeline_dedupe_ratio`, `pipeline_last_query`,
`pipeline_last_result_count`, `pipeline_source_errors` — the Pipeline health
panel renders them.

Override the endpoint with `VITE_STATUS_URL=http://localhost:8000/status`.

The UI maps connection keys to categories in `src/api.ts` (`SERVICE_MAP`):
data sources (pubmed/arxiv/biorxiv), Redis integrations (redis/redisvl), and
external APIs (anthropic/consumer). Connections render as a single list,
sorted and color-coded by type.

## Metrics shown

| Metric | Description |
|--------|-------------|
| **Files processed (1h)** | Papers through the agent loop in the last hour |
| **Connections healthy** | Healthy / total monitored services (exact fraction, not rounded) |
| **New papers seen** | Distinct new papers observed (also logged to CSV) |
| Alerts fired (1h) | Proactive alerts broadcast via SSE |
| Corpus index docs | RedisVL document count |
| Stream queue | `baskr:new_papers` length + pending |
| Memory records | Agent Memory LTM count |
| LangCache hit rate | Query panel cache efficiency |
| Last processed | Most recent agent loop completion |

Without a reachable backend the UI shows an **"Awaiting backend"** empty state
(no mock data) and polls `GET /status` until it responds.
