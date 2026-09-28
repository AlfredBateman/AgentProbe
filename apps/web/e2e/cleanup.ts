import { execFileSync } from "node:child_process";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "../../..");

/**
 * Deletes the fixed e2e test account (scripts/cleanup_e2e_account.py), cascading to whatever
 * it created (projects, agents, suites, API keys). Call this from every spec's `test.afterAll`
 * so the next spec — or the next run of this one — can register the same address again.
 */
export function cleanupE2eAccount(): void {
  // Not --env-file .env: that would load the dev DATABASE_URL and delete nothing from the test
  // database the e2e suite actually runs against (playwright.config.ts points the API at
  // TEST_DATABASE_URL). DATABASE_URL here overrides whatever a loaded .env already set.
  execFileSync("uv", ["run", "python", "scripts/cleanup_e2e_account.py"], {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: { ...process.env, DATABASE_URL: process.env.TEST_DATABASE_URL },
  });
}
