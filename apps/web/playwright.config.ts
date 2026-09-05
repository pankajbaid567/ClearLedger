import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:3120",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 }, acceptDownloads: true },
    },
  ],
  webServer: [
    {
      command:
        "APP_MODE=local_demo AI_ENABLED=false DATABASE_URL=postgresql+psycopg://clearledger:clearledger@localhost:5432/clearledger WEB_ORIGIN=http://localhost:3120 .venv/bin/uvicorn apps.api.app.main:app --host 127.0.0.1 --port 18100",
      cwd: "../..",
      url: "http://127.0.0.1:18100/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "NEXT_DIST_DIR=.next-e2e pnpm start --hostname 127.0.0.1 --port 3120",
      url: "http://127.0.0.1:3120",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
