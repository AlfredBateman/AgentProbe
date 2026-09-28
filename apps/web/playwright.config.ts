import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// e2e tests need both dev servers up: `pnpm dev:api` (Neon dev DB) and `pnpm dev:web`, plus
// demo agents on :9100 (started here). The API must allow private targets (ALLOW_PRIVATE_TARGETS=1).
// reuseExistingServer lets a developer start them once and iterate without a restart per run.
const repoRoot = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run python -m agentprobe_demo_agents",
      cwd: repoRoot,
      url: "http://127.0.0.1:9100/health",
      env: { DEMO_AGENTS_PORT: "9100", FLAKY_RATE: "0.5" },
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm run dev:api",
      cwd: repoRoot,
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm run dev",
      cwd: __dirname,
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
