import type { ConnectionStatus } from "../types";

const STATUS_STYLES: Record<ConnectionStatus, string> = {
  healthy: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
  degraded: "bg-amber-500/20 text-amber-400 border-amber-500/40",
  down: "bg-red-500/20 text-red-400 border-red-500/40",
  unknown: "bg-slate-500/20 text-slate-400 border-slate-500/40",
};

export function StatusBadge({ status }: { status: ConnectionStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs uppercase tracking-wide ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

export function StatusDot({ status }: { status: ConnectionStatus }) {
  const colors: Record<ConnectionStatus, string> = {
    healthy: "bg-emerald-400",
    degraded: "bg-amber-400",
    down: "bg-red-400",
    unknown: "bg-slate-500",
  };
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${colors[status]}`}
      aria-hidden
    />
  );
}

export function formatRelativeTime(iso?: string): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60_000) return "just now";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}h ago`;
  return new Date(iso).toLocaleString();
}
