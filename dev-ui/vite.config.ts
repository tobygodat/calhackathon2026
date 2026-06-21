import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    proxy: {
      "/api": {
        // Pin to IPv4. On Windows, Node resolves "localhost" to ::1 first, which
        // can silently hit a stale backend on the IPv6 loopback. 127.0.0.1 always
        // reaches the uvicorn started with --host 127.0.0.1 --port 8002.
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
