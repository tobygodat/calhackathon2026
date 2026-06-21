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

Expected response shape:

```json
{
  "healthy": true,
  "connections": {
    "redis": { "ok": true, "latency_ms": 12 },
    "redisvl": { "ok": true, "detail": "842 docs" },
    "streams": { "ok": true },
    "agent_memory": { "ok": true },
    "langcache": { "ok": true },
    "openai": { "ok": true },
    "anthropic": { "ok": true, "status": "unknown" },
    "pubmed": { "ok": true },
    "consumer": { "ok": true }
  },
  "metrics": {
    "papers_processed_last_hour": 2,
    "papers_processed_total": 47,
    "alerts_fired_last_hour": 1,
    "corpus_index_docs": 842,
    "stream_length": 3,
    "stream_pending": 0,
    "memory_records": 8,
    "langcache_hit_rate": 0.42,
    "last_processed_at": "2026-06-20T14:32:00Z",
    "consumer_last_heartbeat": "2026-06-20T14:35:00Z"
  },
  "redis_sources": ["RedisVL", "Streams", "Agent Memory", "LangCache"]
}
```

Override the endpoint with `VITE_STATUS_URL=http://localhost:8000/status`.

## Metrics shown

| Metric | Description |
|--------|-------------|
| **Files processed (1h)** | Papers through the agent loop in the last hour |
| **Connections healthy %** | Share of monitored services reporting OK |
| Alerts fired (1h) | Proactive alerts broadcast via SSE |
| Corpus index docs | RedisVL document count |
| Stream queue | `baskr:new_papers` length + pending |
| Memory records | Agent Memory LTM count |
| LangCache hit rate | Query panel cache efficiency |
| Last processed | Most recent agent loop completion |

Without a backend, the UI shows animated mock data (amber badge).
