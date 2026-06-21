import { useEffect, useState } from "react";
import { fetchDigestHistory, fetchPipeline, fetchProfile, fetchSearch } from "../api";
import type { SystemStatus } from "../types";

type CapStatus = "done" | "working" | "not" | "probing";

interface Capability {
  name: string;
  description: string;
  status: CapStatus;
  detail?: string;
}

const STATUS_STYLES: Record<CapStatus, string> = {
  done: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  working: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  not: "bg-slate-600/20 text-slate-500 border-slate-600/30",
  probing: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

const STATUS_LABEL: Record<CapStatus, string> = {
  done: "done",
  working: "working",
  not: "not yet",
  probing: "…",
};

function CapRow({ cap }: { cap: Capability }) {
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-slate-800 last:border-0">
      <span
        className={`inline-flex w-16 justify-center rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest ${STATUS_STYLES[cap.status]}`}
      >
        {STATUS_LABEL[cap.status]}
      </span>
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium text-slate-200">{cap.name}</span>
        <span className="ml-2 text-xs text-slate-500">{cap.description}</span>
      </div>
      {cap.detail && (
        <span className="text-xs text-slate-600 truncate max-w-[200px]">{cap.detail}</span>
      )}
    </div>
  );
}

interface CapabilityPanelProps {
  status: SystemStatus | null;
}

export function CapabilityPanel({ status }: CapabilityPanelProps) {
  const [caps, setCaps] = useState<Capability[]>([
    { name: "Lab Profile", description: "GET /api/profile", status: "probing" },
    { name: "Active Search", description: "POST /api/search", status: "probing" },
    { name: "Digest History", description: "GET /api/digest/history", status: "probing" },
    { name: "Ingest / Pipeline", description: "POST /api/pipeline/search", status: "probing" },
    { name: "Agent Loop", description: "Redis Streams consumer", status: "probing" },
  ]);

  useEffect(() => {
    async function probe() {
      const [profile, searchHits, digestHistory, pipelineResult] = await Promise.all([
        fetchProfile(),
        fetchSearch("gut microbiome fiber"),
        fetchDigestHistory(),
        fetchPipeline({ query: "gut microbiome", days: 7, max_results: 5 }),
      ]);

      setCaps((prev) => [
        {
          ...prev[0],
          status: profile && profile.items.length > 0 ? "done" : profile ? "working" : "not",
          detail: profile
            ? `${profile.items.length} items · ${profile.display_name}`
            : "endpoint not reachable",
        },
        {
          ...prev[1],
          status: searchHits !== null ? "working" : "not",
          detail: searchHits !== null
            ? `${searchHits.length} relevant hits returned`
            : "endpoint not reachable",
        },
        {
          ...prev[2],
          status: digestHistory && digestHistory.length > 0 ? "done" : digestHistory ? "working" : "not",
          detail: digestHistory
            ? `${digestHistory.length} frozen digest${digestHistory.length !== 1 ? "s" : ""}`
            : "endpoint not reachable",
        },
        {
          ...prev[3],
          status: pipelineResult && pipelineResult.papers.length > 0 ? "working" : "not",
          detail: pipelineResult
            ? `${pipelineResult.papers.length} papers · ${Object.entries(pipelineResult.counts).map(([k, v]) => `${k}:${v}`).join(", ")}`
            : "endpoint not reachable",
        },
        {
          ...prev[4],
          status: status?.connections.find((c) => c.id === "fastapi")?.status === "healthy"
            ? "working"
            : "not",
          detail: "Phase 6 — not yet implemented",
        },
      ]);
    }

    probe();
  }, [status]);

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Capabilities
        <span className="ml-2 text-xs font-normal normal-case text-slate-600">
          live endpoint probes
        </span>
      </h2>
      <div>
        {caps.map((cap) => (
          <CapRow key={cap.name} cap={cap} />
        ))}
      </div>
    </section>
  );
}
