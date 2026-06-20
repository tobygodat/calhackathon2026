import type { ServiceConnection, SystemStatus } from "./types";

const SERVICE_DEFS: Omit<ServiceConnection, "status" | "latencyMs" | "detail">[] = [
  { id: "pubmed", label: "PubMed / NCBI", category: "source" },
  { id: "redis", label: "Redis Cloud", category: "redis" },
  { id: "redisvl", label: "RedisVL (corpus index)", category: "redis" },
  { id: "streams", label: "Redis Streams", category: "redis" },
  { id: "agent_memory", label: "Agent Memory", category: "redis" },
  { id: "langcache", label: "LangCache", category: "redis" },
  { id: "openai", label: "OpenAI Embeddings", category: "api" },
  { id: "anthropic", label: "Anthropic Claude", category: "api" },
  { id: "fastapi", label: "FastAPI + Agent Consumer", category: "api" },
];

function randomStatus(): "healthy" | "degraded" | "down" {
  const r = Math.random();
  if (r > 0.92) return "down";
  if (r > 0.85) return "degraded";
  return "healthy";
}

function healthyPercent(connections: ServiceConnection[]): number {
  if (connections.length === 0) return 0;
  const healthy = connections.filter((c) => c.status === "healthy").length;
  return Math.round((healthy / connections.length) * 100);
}

export function generateMockStatus(): SystemStatus {
  const connections: ServiceConnection[] = SERVICE_DEFS.map((def) => {
    const status = randomStatus();
    return {
      ...def,
      status,
      latencyMs: status === "down" ? undefined : Math.floor(Math.random() * 180) + 8,
      detail:
        status === "healthy"
          ? "OK"
          : status === "degraded"
            ? "Slow response"
            : "Unreachable",
    };
  });

  const filesProcessedLastHour = Math.floor(Math.random() * 6);

  return {
    healthy: connections.every(
      (c) => c.status === "healthy" || c.id === "langcache" || c.id === "anthropic",
    ),
    connections,
    metrics: {
      filesProcessedLastHour,
      filesProcessedTotal: 47 + filesProcessedLastHour,
      connectionsHealthyPercent: healthyPercent(connections),
      alertsFiredLastHour: Math.floor(Math.random() * 3),
      corpusIndexDocs: 842,
      streamQueueLength: Math.floor(Math.random() * 5),
      streamPending: Math.floor(Math.random() * 2),
      memoryRecords: 8 + Math.floor(Math.random() * 4),
      langCacheHitRate: 0.34 + Math.random() * 0.2,
      lastProcessedAt: new Date(Date.now() - Math.random() * 3600_000).toISOString(),
      consumerLastHeartbeat: new Date(Date.now() - Math.random() * 30_000).toISOString(),
    },
    redisSources: ["RedisVL", "Streams", "Agent Memory", "LangCache"],
    fetchedAt: new Date().toISOString(),
    source: "mock",
  };
}

export const INITIAL_MOCK_STATUS = generateMockStatus();
