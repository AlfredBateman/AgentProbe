import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { E2E_EMAIL, INVALID_YAML_EMAIL, MAIN_FLOW_EMAIL, SSRF_EMAIL, VISUAL_EMAIL } from "./e2e/fixtures";

// A local .env (see .env.example) supplies TEST_DATABASE_URL and friends; CI sets them directly
// as job env vars instead, so a missing .env there is fine.
try {
  process.loadEnvFile(path.resolve(__dirname, "../../.env"));
} catch {
  // no .env — CI, or a shell that already exported everything.
}

const repoRoot = path.resolve(__dirname, "../..");
const WEB_PORT = 3010;
const API_PORT = 8100;
const DEMO_AGENTS_PORT = 9100;

// e2e tests run against their own dedicated ports and TEST_DATABASE_URL, never the ports or
// database a developer's own `pnpm dev:api`/`pnpm dev:web` use — reusing those would silently
// run against the dev database instead. `scripts/reset-e2e-db.mjs` (migrate + full reset) runs
// once per `pnpm e2e` invocation, chained with && ahead of `playwright test` itself (not a
// Playwright globalSetup: see that script for why), so every run starts from an empty database;
// SIGNUP_ALLOWED_EMAILS lists exactly the fixed addresses the spec files register (see
// e2e/fixtures.ts).
const signupAllowedEmails = [E2E_EMAIL, MAIN_FLOW_EMAIL, SSRF_EMAIL, INVALID_YAML_EMAIL, VISUAL_EMAIL].join(",");

// Fake, committed, test-only values (never used for anything real): Fernet needs a valid key
// even for throwaway ciphertext, and JWT_SECRET just needs to be 32+ characters.
const FALLBACK_ENCRYPTION_KEY = "1l6VfZOVa0Y9eS9RXFNoOP8YWhN9tRxd4TwLvXKlUpk=";
const FALLBACK_JWT_SECRET = "e2e-fixed-test-secret-never-used-for-anything-real-0123456789";

const apiEnv = {
  DATABASE_URL: process.env.TEST_DATABASE_URL ?? "",
  QUEUE_BACKEND: "inline",
  LLM_PROVIDER: "mock",
  AGENT_MODE: "mock",
  ALLOW_PRIVATE_TARGETS: "1",
  SIGNUP_ALLOWED_EMAILS: signupAllowedEmails,
  WEB_ORIGIN: `http://localhost:${WEB_PORT}`,
  JWT_SECRET: process.env.JWT_SECRET || FALLBACK_JWT_SECRET,
  ENCRYPTION_KEY: process.env.ENCRYPTION_KEY || FALLBACK_ENCRYPTION_KEY,
  COOKIE_SECURE: "1", // Chrome treats http://localhost as a secure context
  // Every spec signs in from 127.0.0.1: 13 register/login calls in about half a minute, right at
  // the production default's edge (10 per minute per IP, refilling one per 6 s), so the last
  // spec's login got a 429 depending on timing. The limiter has its own API tests; no spec here
  // tests it.
  AUTH_RATE_LIMIT_PER_MINUTE: "1000",
  LOG_LEVEL: "WARNING",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run python -m agentprobe_demo_agents",
      cwd: repoRoot,
      url: `http://127.0.0.1:${DEMO_AGENTS_PORT}/health`,
      env: { DEMO_AGENTS_PORT: String(DEMO_AGENTS_PORT), FLAKY_RATE: "0.5" },
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `uv run uvicorn agentprobe_api.main:app --port ${API_PORT} --loop asyncio:SelectorEventLoop`,
      cwd: repoRoot,
      url: `http://localhost:${API_PORT}/health`,
      env: apiEnv,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      // A production build, not `next dev`: Next refuses a second dev server in the same
      // project directory regardless of port (it locks on the directory, not the port), which
      // would collide with a developer's own `pnpm dev:web` on :3000. `next start` has no such
      // restriction. NEXT_PUBLIC_API_URL is inlined at build time, so it's set here too, not
      // just for `next start`.
      command: `pnpm exec next build && pnpm exec next start -p ${WEB_PORT}`,
      cwd: __dirname,
      url: `http://localhost:${WEB_PORT}`,
      env: { API_INTERNAL_URL: `http://localhost:${API_PORT}`, NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
