// Three-panel layout (SPEC §9). Dark research-tool styling.
import LabProfilePanel from "./components/LabProfilePanel";
import ActiveSearchPanel from "./components/ActiveSearchPanel";
import DigestHistoryPanel from "./components/DigestHistoryPanel";

export default function App() {
  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4">
        <h1 className="text-xl font-semibold">Baskr</h1>
        <p className="text-sm text-neutral-400">Research radar · gut microbiome</p>
      </header>
      <main className="grid grid-cols-1 gap-4 p-6 lg:grid-cols-3">
        <LabProfilePanel />
        <ActiveSearchPanel />
        <DigestHistoryPanel />
      </main>
    </div>
  );
}
