import { useRef, useState } from "react";
import { dropIntakeFiles } from "../api";
import type { IntakeResult } from "../types";

export function IntakeTestPanel({ onIngested }: { onIngested: () => void }) {
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState<IntakeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function submit(files: File[]) {
    if (files.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    const res = await dropIntakeFiles(files);
    if (res) {
      setResult(res);
      onIngested();
    } else {
      setError("Intake request failed — check the backend is reachable.");
    }
    setBusy(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    void submit(files);
  }

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files ? Array.from(e.target.files) : [];
    void submit(files);
    e.target.value = "";
  }

  const errorEntries = result ? Object.entries(result.errors) : [];

  return (
    <section className="rounded-lg border border-slate-700 bg-slate-900 p-5">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-widest text-slate-400">
        Intake tester
      </h2>
      <p className="mb-4 text-xs text-slate-600">
        Drop JSON paper files straight into the intake stream to exercise the
        pipeline.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${
          dragOver
            ? "border-cyan-400 bg-cyan-500/10"
            : "border-slate-700 bg-slate-900/40 hover:border-slate-600"
        }`}
      >
        <p className="text-sm text-slate-300">
          {busy ? "Streaming…" : "Drop .json files here"}
        </p>
        <p className="mt-1 text-xs text-slate-600">or click to choose files</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".json,application/json"
          onChange={handleSelect}
          className="hidden"
        />
      </div>

      {error && <p className="mt-3 text-xs text-amber-400">{error}</p>}

      {result && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded border border-slate-700 bg-slate-800/60 p-2">
              <p className="text-lg font-semibold tabular-nums text-cyan-300">
                {result.streamed}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                streamed
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/60 p-2">
              <p className="text-lg font-semibold tabular-nums text-emerald-300">
                {result.recorded}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                recorded
              </p>
            </div>
            <div className="rounded border border-slate-700 bg-slate-800/60 p-2">
              <p className="text-lg font-semibold tabular-nums text-slate-300">
                {result.skipped}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-slate-500">
                skipped
              </p>
            </div>
          </div>

          {errorEntries.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-slate-600">
                Per-file errors
              </p>
              {errorEntries.map(([file, msg]) => (
                <p
                  key={file}
                  className="rounded border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs text-red-300"
                >
                  <span className="font-mono">{file}</span>: {msg}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
