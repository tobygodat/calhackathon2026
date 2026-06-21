export function RedisSourcesPanel({ sources }: { sources: string[] }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-medium text-slate-400">
        Active Redis surfaces
      </h2>
      {sources.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {sources.map((source) => (
            <span
              key={source}
              className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1 text-sm text-red-300"
            >
              {source}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-600">
          No active surfaces reported — wire up Redis and restart the backend.
        </p>
      )}
    </section>
  );
}
