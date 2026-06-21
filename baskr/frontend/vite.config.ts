import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api to the FastAPI backend during dev (SPEC §8).
// Pin to IPv4 — on Windows, "localhost" resolves to ::1 first which can miss
// the uvicorn process started with --host 127.0.0.1 --port 8002.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
      },
    },
  },
});
