import type {
  IntakeResult,
  LedgerEntry,
  Paper,
  Profile,
  ScorecardResult,
  ServiceConnection,
  StatusResponse,
  SystemMetrics,
  SystemStatus,
} from "./types";

const API_URL = import.meta.env.VITE_STATUS_URL ?? "/api/status";

const SERVICE_MAP: Record<
  string,
  { id: string; label: string; category: ServiceConnection["category"] }
> = {
  pubmed: { id: "pubmed", label: "PubMed / NCBI", category: "source" },
  ncbi: { id: "pubmed", label: "PubMed / NCBI", category: "source" },
  arxiv: { id: "arxiv", label: "arXiv", category: "source" },
  biorxiv: { id: "biorxiv", label: "bioRxiv", category: "source" },
  medrxiv: { id: "medrxiv", label: "medRxiv", category: "source" },
  openalex: { id: "openalex", label: "OpenAlex", category: "source" },
  chemrxiv: { id: "chemrxiv", label: "ChemRxiv", category: "source" },
  redis: { id: "redis", label: "Redis Cloud", category: "redis" },
  redisvl: { id: "redisvl", label: "RedisVL (corpus index)", category: "redis" },
  stream: { id: "streams", label: "Redis Streams", category: "redis" },
  streams: { id: "streams", label: "Redis Streams", category: "redis" },
  agent_memory: { id: "agent_memory", label: "Agent Memory", category: "redis" },
  langcache: { id: "langcache", label: "LangCache", category: "redis" },
  anthropic: { id: "anthropic", label: "Anthropic Claude", category: "api" },
  consumer: { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
  fastapi: { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
};

export const EXPECTED_SERVICES: Array<{
  id: string;
  label: string;
  category: ServiceConnection["category"];
}> = [
  { id: "pubmed", label: "PubMed / NCBI", category: "source" },
  { id: "arxiv", label: "arXiv", category: "source" },
  { id: "biorxiv", label: "bioRxiv", category: "source" },
  { id: "medrxiv", label: "medRxiv", category: "source" },
  { id: "openalex", label: "OpenAlex", category: "source" },
  { id: "chemrxiv", label: "ChemRxiv", category: "source" },
  { id: "redis", label: "Redis Cloud", category: "redis" },
  { id: "redisvl", label: "RedisVL (corpus index)", category: "redis" },
  { id: "anthropic", label: "Anthropic Claude", category: "api" },
  { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
];

function emptyMetrics(): SystemMetrics {
  return {
    connectionsHealthy: 0,
    connectionsTotal: EXPECTED_SERVICES.length,
    newPapersSeen: 0,
    newPapersLastHour: 0,
    lastNewPaperAt: undefined,
    secondsSinceLastNewPaper: undefined,
    statusFlipCounts: {},
    statusFlipSeries: [],
    alertsFiredLastHour: 0,
    corpusIndexDocs: 0,
    streamQueueLength: 0,
    streamPending: 0,
    memoryRecords: 0,
    langCacheHitRate: undefined,
    lastProcessedAt: undefined,
    consumerLastHeartbeat: undefined,
    batchVectorSearch: 0,
    batchLlmScan: 0,
    stageCounts: {},
    sourceContacts: {},
    stableWindowS: undefined,
    heartbeatIntervalS: undefined,
    heartbeatLastTick: undefined,
  };
}

export function offlineStatus(): SystemStatus {
  return {
    healthy: false,
    connections: EXPECTED_SERVICES.map((s) => ({
      id: s.id,
      label: s.label,
      category: s.category,
      status: "down" as const,
    })),
    metrics: emptyMetrics(),
    redisSources: [],
    fetchedAt: new Date().toISOString(),
    source: "offline",
  };
}

function mapConnectionStatus(
  ok: boolean,
  status?: string,
): ServiceConnection["status"] {
  if (status === "degraded") return "degraded";
  if (status === "unknown") return "unknown";
  if (status === "ready") return "ready";
  return ok ? "healthy" : "down";
}

function normalizeConnections(
  raw: StatusResponse["connections"],
): ServiceConnection[] {
  return Object.entries(raw).map(([key, value]) => {
    const meta = SERVICE_MAP[key.toLowerCase()] ?? {
      id: key,
      label: key,
      category: "api" as const,
    };
    return {
      id: meta.id,
      label: meta.label,
      category: meta.category,
      status: mapConnectionStatus(value.ok, value.status),
      latencyMs: value.latency_ms,
      detail: value.detail,
    };
  });
}

function normalizeStatus(data: StatusResponse): SystemStatus {
  const connections = normalizeConnections(data.connections);
  const m = data.metrics;

  return {
    healthy: data.healthy,
    connections,
    metrics: {
      connectionsHealthy: connections.filter(
        (c) => c.status === "healthy" || c.status === "ready",
      ).length,
      connectionsTotal: connections.length,
      newPapersSeen: m.new_papers_seen ?? 0,
      newPapersLastHour: m.new_papers_last_hour ?? 0,
      lastNewPaperAt: m.last_new_paper_at ?? undefined,
      secondsSinceLastNewPaper: m.seconds_since_last_new_paper ?? undefined,
      statusFlipCounts: m.status_flip_counts ?? {},
      statusFlipSeries: m.status_flip_series ?? [],
      alertsFiredLastHour: m.alerts_fired_last_hour ?? 0,
      corpusIndexDocs: m.corpus_index_docs ?? 0,
      streamQueueLength: m.stream_length ?? 0,
      streamPending: m.stream_pending ?? 0,
      memoryRecords: m.memory_records ?? 0,
      langCacheHitRate: m.langcache_hit_rate,
      lastProcessedAt: m.last_processed_at,
      consumerLastHeartbeat: m.consumer_last_heartbeat,
      batchVectorSearch: m.batch_vector_search ?? 0,
      batchLlmScan: m.batch_llm_scan ?? 0,
      stageCounts: m.stage_counts ?? {},
      sourceContacts: m.source_contacts ?? {},
      stableWindowS: m.stable_window_s,
      heartbeatIntervalS: m.heartbeat_interval_s,
      heartbeatLastTick: m.heartbeat_last_tick,
    },
    redisSources: data.redis_sources ?? [],
    fetchedAt: new Date().toISOString(),
    source: "live",
  };
}

export async function fetchProfile(): Promise<Profile | null> {
  try {
    const res = await fetch("/api/profile", { signal: AbortSignal.timeout(8_000) });
    if (!res.ok) return null;
    return (await res.json()) as Profile;
  } catch {
    return null;
  }
}

export async function fetchLedger(): Promise<LedgerEntry[] | null> {
  try {
    const res = await fetch("/api/ledger", { signal: AbortSignal.timeout(8_000) });
    if (!res.ok) return null;
    return (await res.json()) as LedgerEntry[];
  } catch {
    return null;
  }
}

export async function dropIntakeFiles(files: File[]): Promise<IntakeResult | null> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  try {
    const res = await fetch("/api/intake", {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return {
        streamed: 0,
        recorded: 0,
        skipped: 0,
        errors: { request: text || res.statusText },
        ids: [],
      };
    }
    return (await res.json()) as IntakeResult;
  } catch (err) {
    return {
      streamed: 0,
      recorded: 0,
      skipped: 0,
      errors: { request: err instanceof Error ? err.message : "Unknown error" },
      ids: [],
    };
  }
}

export async function runIntakeTest(
  files: File[],
): Promise<ScorecardResult | null> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  try {
    const res = await fetch("/api/intake/test", {
      method: "POST",
      body: form,
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as ScorecardResult;
  } catch {
    return null;
  }
}

export interface PipelineSearchResult {
  papers: Paper[];
  counts: Record<string, number>;
  errors: Record<string, string>;
}

export async function runPipelineSearch(
  query: string,
  days = 7,
  maxResults = 25,
): Promise<PipelineSearchResult | null> {
  try {
    const res = await fetch("/api/pipeline/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, days, max_results: maxResults }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as PipelineSearchResult;
  } catch {
    return null;
  }
}

export async function fetchStatus(): Promise<SystemStatus | null> {
  try {
    const res = await fetch(API_URL, { signal: AbortSignal.timeout(9000) });
    if (!res.ok) return null;
    const data = (await res.json()) as StatusResponse;
    return normalizeStatus(data);
  } catch {
    return null;
  }
}
