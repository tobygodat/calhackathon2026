import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api to the FastAPI backend during dev (SPEC §8).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Pin to IPv4 + the canonical 8002 the backend actually runs on. On Windows,
      // Node resolves "localhost" to ::1 first, which can silently miss the uvicorn
      // started with --host 127.0.0.1 --port 8002. (Matches dev-ui/vite.config.ts.)
      "/api": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
        proxyTimeout: 3000,
        timeout: 3000,
      },
    },
  },
});
