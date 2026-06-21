import type {
  DigestEntry,
  DigestSummary,
  PipelineSearchRequest,
  PipelineSearchResult,
  Profile,
  SearchHit,
  ServiceConnection,
  StatusResponse,
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
  biorxiv: { id: "biorxiv", label: "bioRxiv / medRxiv", category: "source" },
  medrxiv: { id: "biorxiv", label: "bioRxiv / medRxiv", category: "source" },
  // WARNING: NATURE SOURCE IS DISABLED — DO NOT RE-ENABLE WITHOUT EXPLICIT REQUEST
  // nature: { id: "nature", label: "Nature / Springer", category: "source" },
  // springer: { id: "nature", label: "Nature / Springer", category: "source" },
  redis: { id: "redis", label: "Redis Cloud", category: "redis" },
  redisvl: { id: "redisvl", label: "RedisVL (corpus index)", category: "redis" },
  stream: { id: "streams", label: "Redis Streams", category: "redis" },
  streams: { id: "streams", label: "Redis Streams", category: "redis" },
  agent_memory: { id: "agent_memory", label: "Agent Memory", category: "redis" },
  langcache: { id: "langcache", label: "LangCache", category: "redis" },
  openai: { id: "openai", label: "OpenAI Embeddings", category: "api" },
  anthropic: { id: "anthropic", label: "Anthropic Claude", category: "api" },
  consumer: { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
  fastapi: { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
};

function mapConnectionStatus(
  ok: boolean,
  status?: string,
): ServiceConnection["status"] {
  if (status === "degraded") return "degraded";
  if (status === "unknown") return "unknown";
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

function healthyPercent(connections: ServiceConnection[]): number {
  if (connections.length === 0) return 0;
  const healthy = connections.filter((c) => c.status === "healthy").length;
  return Math.round((healthy / connections.length) * 100);
}

function normalizeStatus(data: StatusResponse): SystemStatus {
  const connections = normalizeConnections(data.connections);
  const m = data.metrics;

  return {
    healthy: data.healthy,
    connections,
    metrics: {
      filesProcessedLastHour: m.papers_processed_last_hour ?? 0,
      filesProcessedTotal: m.papers_processed_total ?? 0,
      connectionsHealthyPercent: healthyPercent(connections),
      alertsFiredLastHour: m.alerts_fired_last_hour ?? 0,
      corpusIndexDocs: m.corpus_index_docs ?? 0,
      streamQueueLength: m.stream_length ?? 0,
      streamPending: m.stream_pending ?? 0,
      memoryRecords: m.memory_records ?? 0,
      langCacheHitRate: m.langcache_hit_rate,
      lastProcessedAt: m.last_processed_at,
      consumerLastHeartbeat: m.consumer_last_heartbeat,
      // Pipeline-specific pass-through
      pipelineSourceCounts: m.pipeline_source_counts,
      pipelineDedupeRatio: m.pipeline_dedupe_ratio,
      pipelineLastQuery: m.pipeline_last_query,
      pipelineLastResultCount: m.pipeline_last_result_count,
      pipelineSourceErrors: m.pipeline_source_errors,
    },
    redisSources: data.redis_sources ?? [],
    fetchedAt: new Date().toISOString(),
    source: "live",
  };
}

const PIPELINE_URL = import.meta.env.VITE_PIPELINE_URL ?? "/api/pipeline/search";

export async function fetchPipeline(
  req: PipelineSearchRequest,
): Promise<PipelineSearchResult | null> {
  try {
    const res = await fetch(PIPELINE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return { papers: [], errors: { request: text || res.statusText }, counts: {} };
    }
    return (await res.json()) as PipelineSearchResult;
  } catch (err) {
    return {
      papers: [],
      errors: { request: err instanceof Error ? err.message : "Unknown error" },
      counts: {},
    };
  }
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

export async function fetchSearch(question: string): Promise<SearchHit[] | null> {
  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as SearchHit[];
  } catch {
    return null;
  }
}

export async function fetchDigestHistory(): Promise<DigestSummary[] | null> {
  try {
    const res = await fetch("/api/digest/history", {
      signal: AbortSignal.timeout(8_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as DigestSummary[];
  } catch {
    return null;
  }
}

export async function fetchDigest(date: string): Promise<DigestEntry[] | null> {
  try {
    const res = await fetch(`/api/digest/${date}`, {
      signal: AbortSignal.timeout(8_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as DigestEntry[];
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
