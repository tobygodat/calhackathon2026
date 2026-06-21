export type ConnectionStatus = "healthy" | "degraded" | "down" | "unknown";

export interface ServiceConnection {
  id: string;
  label: string;
  category: "source" | "redis" | "api";
  status: ConnectionStatus;
  latencyMs?: number;
  detail?: string;
}

export interface SystemMetrics {
  filesProcessedLastHour: number;
  filesProcessedTotal: number;
  connectionsHealthyPercent: number;
  alertsFiredLastHour: number;
  corpusIndexDocs: number;
  streamQueueLength: number;
  streamPending: number;
  memoryRecords: number;
  langCacheHitRate?: number;
  lastProcessedAt?: string;
  consumerLastHeartbeat?: string;
}

export interface SystemStatus {
  healthy: boolean;
  connections: ServiceConnection[];
  metrics: SystemMetrics;
  redisSources: string[];
  fetchedAt: string;
  source: "live";
}

export type PipelineSource = "pubmed" | "arxiv" | "biorxiv" | "nature";

export interface Paper {
  source: PipelineSource;
  source_id: string;
  title: string;
  abstract: string;
  authors: string[];
  doi: string | null;
  url: string | null;
  journal: string | null;
  published: string; // YYYY-MM-DD
  categories: string[];
}

export interface PipelineSearchRequest {
  query: string;
  days?: number;
  sources?: PipelineSource[];
  max_results?: number;
}

export interface PipelineSearchResult {
  papers: Paper[];
  errors: Record<string, string>;
  counts: Record<string, number>;
}

export interface StatusResponse {
  healthy: boolean;
  connections: Record<
    string,
    { ok: boolean; latency_ms?: number; detail?: string; status?: string }
  >;
  metrics: {
    papers_processed_last_hour?: number;
    papers_processed_total?: number;
    alerts_fired_last_hour?: number;
    corpus_index_docs?: number;
    stream_length?: number;
    stream_pending?: number;
    memory_records?: number;
    langcache_hit_rate?: number;
    last_processed_at?: string;
    consumer_last_heartbeat?: string;
  };
  redis_sources?: string[];
}
