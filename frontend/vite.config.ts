import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// In dev the UI runs on :5173 and the agent on :8000, so every API path the
// client touches is proxied — that keeps the client's fetch calls origin-relative
// and identical in dev and prod (where FastAPI serves this bundle itself).
const AGENT = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": AGENT,
      "/apps": AGENT,
      "/run_sse": AGENT,
      "/list-apps": AGENT,
    },
  },
  build: {
    outDir: "dist",
    // Split the vendor chunk so a UI edit doesn't bust the whole cache.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          motion: ["motion"],
        },
      },
    },
  },
});
