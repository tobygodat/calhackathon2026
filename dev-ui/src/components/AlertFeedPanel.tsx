import { useEffect, useRef, useState } from "react";
import { LabelBadge } from "./LabelBadge";
import type { Label } from "../types";

interface Alert {
  paper_title: string;
  paper_source: string;
  paper_url: string | null;
  label: Label;
  reason: string;
  confidence: number;
  matched_item_id: string | null;
  fired_at: string;
}

export function AlertFeedPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource("/api/alerts/stream");
    esRef.current = es;

    es.onopen = () => {
      setConnected(true);
      setError(null);
    };

    es.onmessage = (ev) => {
      try {
        const alert = JSON.parse(ev.data) as Alert;
        setAlerts((prev) => [alert, ...prev].slice(0, 50));
      } catch {
        // heartbeat comment or malformed — ignore
      }
    };

    es.onerror = () => {
      setConnected(false);
      setError("SSE connection lost — retrying…");
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-slate-400 flex items-center gap-2">
        Alert Feed
        <span className="ml-1 text-xs font-normal normal-case text-slate-600">
          GET /api/alerts/stream · SSE
        </span>
        <span
          className={`ml-auto h-2 w-2 rounded-full flex-shrink-0 ${
            connected ? "bg-emerald-400" : "bg-slate-600"
          }`}
          title={connected ? "Connected" : "Disconnected"}
        />
      </h2>

      {error && <p className="text-xs text-amber-400 mb-3">{error}</p>}

      {alerts.length === 0 ? (
        <p className="text-xs text-slate-500">
          {connected
            ? "Listening for alerts… Run scripts/demo_stream.py to push papers."
            : "Connecting to SSE stream…"}
        </p>
      ) : (
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {alerts.map((alert, i) => (
            <div
              key={`${alert.fired_at}-${i}`}
              className="rounded border border-slate-700 bg-slate-800/60 p-3 space-y-1.5"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-slate-100 leading-tight flex-1">
                  {alert.paper_url ? (
                    <a
                      href={alert.paper_url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-cyan-300 transition-colors"
                    >
                      {alert.paper_title}
                    </a>
                  ) : (
                    alert.paper_title
                  )}
                </p>
                <LabelBadge label={alert.label} />
              </div>
              <p className="text-xs text-slate-400 border-l-2 border-slate-600 pl-2 leading-relaxed">
                {alert.reason}
              </p>
              <div className="flex items-center gap-3 text-xs text-slate-600">
                <span className="uppercase tracking-wide">{alert.paper_source}</span>
                <span>conf {(alert.confidence * 100).toFixed(0)}%</span>
                {alert.matched_item_id && <span>→ {alert.matched_item_id}</span>}
                <span className="ml-auto font-mono">
                  {new Date(alert.fired_at).toLocaleTimeString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
