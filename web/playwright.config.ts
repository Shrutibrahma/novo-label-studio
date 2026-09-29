import { defineConfig, devices } from "@playwright/test";

/** End-to-end flows 13.1–13.9 against the e2e stack (scripts/test.ps1) and the agent in simulated mode. */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://localhost:9443",
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    timezoneId: "America/Chicago",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
