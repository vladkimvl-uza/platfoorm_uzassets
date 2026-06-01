import { defineConfig, devices } from "@playwright/test";

// E2E-смоук против РАБОТАЮЩЕГО приложения (nginx на https://localhost).
// Переопредели цель: E2E_BASE_URL=https://uz-assets040 npm run e2e
const BASE_URL = process.env.E2E_BASE_URL || "https://localhost";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true, // dev/self-signed TLS
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
