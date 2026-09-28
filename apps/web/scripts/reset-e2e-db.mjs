// Migrates and truncates the e2e test database before Playwright starts anything. Run:
// pnpm --filter web e2e (this script is chained into that script with &&).
//
// Not a Playwright globalSetup: Playwright does not guarantee globalSetup finishes before its
// webServer commands start (observed directly: in CI, against a brand-new empty Postgres
// container, the API's own lifespan startup query ("relation runs does not exist") ran and
// crashed before globalSetup's migration had a chance to create the table — invisible locally
// only because the Neon test branch there already had a schema from previous `pnpm verify`
// runs). Chaining this script with && in package.json guarantees it completes first, full stop.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));

// A local .env (see .env.example) supplies TEST_DATABASE_URL and friends; CI sets them directly
// as job env vars instead, so a missing .env there is fine. playwright.config.ts does the same
// load, but that happens in a separate process from this script, so it can't be skipped here.
try {
  process.loadEnvFile(fileURLToPath(new URL("../../../.env", import.meta.url)));
} catch {
  // no .env — CI, or a shell that already exported everything.
}

const testDatabaseUrl = process.env.TEST_DATABASE_URL;
if (!testDatabaseUrl) {
  console.error(
    "TEST_DATABASE_URL is not set. apps/web's e2e suite runs against a dedicated database, " +
      "never the dev one: set it in .env (see .env.example) or export it before `pnpm e2e`.",
  );
  process.exit(1);
}

// Forced on: reaching this point means we're about to run e2e tests against
// TEST_DATABASE_URL, exactly the condition this flag exists to confirm (mirrors conftest.py's
// guard, which scripts/reset_test_db.py itself also checks independently).
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
