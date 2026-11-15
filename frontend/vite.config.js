import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    // "/" by default. Set VITE_BASE_PATH=/agentic-grc/ when the app is served under a sub-path
    // behind a reverse proxy (see README "Deploying under a sub-path").
    base: env.VITE_BASE_PATH || "/",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 4178,
      strictPort: true,
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.js",
      css: true,
    },
  };
});
