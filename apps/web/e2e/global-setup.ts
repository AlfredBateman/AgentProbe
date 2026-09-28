import { execFileSync } from "node:child_process";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "../../..");

/**
 * Runs once per `pnpm e2e` invocation, before any server in `playwright.config.ts`'s
 * `webServer` list starts: migrates the test database to head, then truncates it (see
 * scripts/reset_test_db.py). Every spec file — and every one of the "3 consecutive passes" the
 * suite is checked against — starts from the same empty database, so no spec needs to register
 * a fresh email or clean up after itself to avoid colliding with a previous run's leftovers.
 */
export default function globalSetup(): void {
  const testDatabaseUrl = process.env.TEST_DATABASE_URL;
  if (!testDatabaseUrl) {
    throw new Error(
      "TEST_DATABASE_URL is not set. apps/web's e2e suite runs against a dedicated database, " +
        "never the dev one: set it in .env (see .env.example) or export it before `pnpm e2e`.",
    );
  }
  // Forced on: reaching this point means we're about to run e2e tests against
  // TEST_DATABASE_URL, exactly the condition this flag exists to confirm (mirrors conftest.py's
  // guard, which reset_test_db.py itself also checks independently).
  const env = { ...process.env, ALLOW_DB_TESTS: "1" };

  execFileSync("uv", ["run", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"], {
    cwd: repoRoot,
    stdio: "inherit",
    env: { ...env, DATABASE_URL: testDatabaseUrl },
  });

  execFileSync("uv", ["run", "python", "scripts/reset_test_db.py"], {
    cwd: repoRoot,
    stdio: "inherit",
    env,
  });
}
