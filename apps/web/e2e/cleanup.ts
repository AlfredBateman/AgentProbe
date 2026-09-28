import { execFileSync } from "node:child_process";
import path from "node:path";

const REPO_ROOT = path.resolve(__dirname, "../../..");

/**
 * Deletes the fixed e2e test account (scripts/cleanup_e2e_account.py), cascading to whatever
 * it created (projects, agents, suites, API keys). Call this from every spec's `test.afterAll`
 * so the next spec — or the next run of this one — can register the same address again.
 */
export function cleanupE2eAccount(): void {
  execFileSync("uv", ["run", "--env-file", ".env", "python", "scripts/cleanup_e2e_account.py"], {
    cwd: REPO_ROOT,
    stdio: "inherit",
  });
}
