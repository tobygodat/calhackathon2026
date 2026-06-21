// Date list from /api/digest/history; clicking loads /api/digest/{date} (SPEC §9).
// TODO: fetch history, render dates, on-click load that day's DigestEntry[].

export default function DigestHistoryPanel() {
  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <h2 className="mb-2 font-medium">Daily Digest</h2>
      <p className="text-sm text-neutral-500">TODO: date list + selected digest.</p>
    </section>
  );
}
