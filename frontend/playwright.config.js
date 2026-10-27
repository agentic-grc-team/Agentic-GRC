import { defineConfig } from "@playwright/test";

const baseURL = "http://127.0.0.1:4179";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.js",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]]
    : "list",
  use: {
    baseURL,
    browserName: "chromium",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4179 --strictPort",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    env: {
      VITE_API_BASE_URL: "/api/v1",
      VITE_SUPABASE_URL: "http://127.0.0.1:54321",
      VITE_SUPABASE_PUBLISHABLE_KEY: "e2e-publishable-key",
    },
  },
});
