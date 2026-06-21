export type ConnectionStatus = "healthy" | "degraded" | "down" | "unknown";

export interface ServiceConnection {
  id: string;
  label: string;
  category: "source" | "redis" | "api";
  status: ConnectionStatus;
  latencyMs?: number;
  detail?: string;
}

export interface PipelineSourceMetrics {
  papers_fetched: number;
  last_fetch_at?: string;
  error?: string;
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
  // Pipeline-specific metrics
  pipelineSourceCounts?: Record<string, number>;
  pipelineDedupeRatio?: number;   // 0-1: (pre-dedupe - post-dedupe) / pre-dedupe
  pipelineLastQuery?: string;
  pipelineLastResultCount?: number;
  pipelineSourceErrors?: Record<string, string>;
}

export interface SystemStatus {
  healthy: boolean;
  connections: ServiceConnection[];
  metrics: SystemMetrics;
  redisSources: string[];
  fetchedAt: string;
  source: "live";
}

// WARNING: NATURE SOURCE IS DISABLED — DO NOT RE-ENABLE WITHOUT EXPLICIT REQUEST
// "nature" has been removed from PipelineSource. Do not add it back unless specifically asked.
export type PipelineSource = "pubmed" | "arxiv" | "biorxiv"; // | "nature"

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

// --- SPEC §5 data models (mirroring models.py) --------------------------------

export type ProfileItemKind =
  | "open_question"
  | "assumption"
  | "finding"
  | "planned_experiment";

export interface ProfileItem {
  id: string;
  kind: ProfileItemKind;
  text: string;
}

export interface Profile {
  lab_id: string;
  niche: string;
  display_name: string;
  items: ProfileItem[];
}

export type Label =
  | "ANSWERS"
  | "CONTRADICTS"
  | "EXTENDS"
  | "NOT_RELEVANT"
  | "SCOOP";

export interface Classification {
  label: Label;
  reason: string;
  matched_item_id: string | null;
  confidence: number;
}

export interface SearchHit {
  paper: Paper;
  classification: Classification;
}

export interface DigestEntry {
  date: string;
  paper: Paper;
  classification: Classification;
}

export interface DigestSummary {
  date: string;
  count: number;
  top_label: Label;
}

// --- StatusResponse (existing, unchanged below) --------------------------------

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
    // Pipeline-specific metrics surfaced by the backend
    pipeline_source_counts?: Record<string, number>;
    pipeline_dedupe_ratio?: number;
    pipeline_last_query?: string;
    pipeline_last_result_count?: number;
    pipeline_source_errors?: Record<string, string>;
  };
  redis_sources?: string[];
}
