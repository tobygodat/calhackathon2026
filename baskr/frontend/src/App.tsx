// App shell. Lightweight hash routing between the Research Dashboard welcome
// screen (#/) and the Lab Context settings page (#/lab-context) — no router
// dependency needed for two routes.
import { useEffect, useState } from "react";
import WelcomeDashboard from "./components/welcome/WelcomeDashboard";
import LabContextPage from "./components/labcontext/LabContextPage";

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
  if (hash.startsWith("#/lab-context")) return <LabContextPage />;
  return <WelcomeDashboard />;
}
