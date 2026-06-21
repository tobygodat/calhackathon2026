import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api to the FastAPI backend during dev (SPEC §8).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
