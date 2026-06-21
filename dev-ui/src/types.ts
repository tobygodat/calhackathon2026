export type ConnectionStatus = "healthy" | "degraded" | "down" | "unknown";

export interface ServiceConnection {
  id: string;
  label: string;
  category: "source" | "redis" | "api";
  status: ConnectionStatus;
  latencyMs?: number;
  detail?: string;
}

export interface LedgerEntry {
  title: string;
  first_seen_at: string;
  source: string;
}

export interface IntakeResult {
  streamed: number;
  recorded: number;
  skipped: number;
  errors: Record<string, string>;
  ids: string[];
}

export interface StatusFlipEvent {
  connection: string;
  changed_at: string;
  transition: "on" | "off";
}

export interface SystemMetrics {
  connectionsHealthy: number;
  connectionsTotal: number;
  newPapersSeen: number;
  newPapersLastHour: number;
  lastNewPaperAt?: string;
  secondsSinceLastNewPaper?: number;
  statusFlipCounts: Record<string, number>;
  statusFlipSeries: StatusFlipEvent[];
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
  source: "live" | "offline";
}

export interface Paper {
  source: string;
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

// --- StatusResponse (existing, unchanged below) --------------------------------

export interface StatusResponse {
  healthy: boolean;
  connections: Record<
    string,
    { ok: boolean; latency_ms?: number; detail?: string; status?: string }
  >;
  metrics: {
    new_papers_seen?: number;
    new_papers_last_hour?: number;
    last_new_paper_at?: string | null;
    seconds_since_last_new_paper?: number | null;
    status_flip_counts?: Record<string, number>;
    status_flip_series?: StatusFlipEvent[];
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
