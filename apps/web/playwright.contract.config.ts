import { defineConfig, devices } from "@playwright/test";

/** Browser contracts use intercepted API responses; no database or API server is started. */
export default defineConfig({
  testDir: "./tests",
  testMatch: "frontend-contract.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://127.0.0.1:3121", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } } }],
  webServer: {
    command: "NEXT_DIST_DIR=.next-playwright pnpm start --hostname 127.0.0.1 --port 3121",
    url: "http://127.0.0.1:3121", reuseExistingServer: false, timeout: 60_000,
  },
});
