// App shell. Lightweight hash routing between the Research Dashboard welcome
// screen (#/), the Lab Context settings page (#/lab-context), and the Flagged
// Papers database (#/flagged) — no router dependency needed for a few routes.
import { useEffect, useState } from "react";
import WelcomeDashboard from "./components/welcome/WelcomeDashboard";
import SearchResultsPage from "./components/welcome/SearchResultsPage";
import LabContextPage from "./components/labcontext/LabContextPage";
import FlaggedPapersPage from "./components/flagged/FlaggedPapersPage";

function useHashRoute() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHashRoute();
  if (hash.startsWith("#/search")) {
    const q = new URLSearchParams(hash.split("?")[1] ?? "").get("q") ?? "";
    return <SearchResultsPage query={q} />;
  }
  if (hash.startsWith("#/lab-context")) return <LabContextPage />;
  if (hash.startsWith("#/flagged")) return <FlaggedPapersPage />;
  return <WelcomeDashboard />;
}
