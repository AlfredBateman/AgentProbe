# Progress

## Done
- 2026-09-24 **Bootstrap**:
  - PLAN.md, CLAUDE.md, ADR 0001 (packages/core), ADR 0002 (web toolchain versions).
  - Monorepo scaffold:
    - uv workspace on Python 3.12: `packages/core`, `packages/cli`, `apps/api`, `demo-agents`.
    - pnpm workspace: `apps/web`, running Next 16.3.6, React 19.3, Tailwind 4.3.
  - `GET /health`.
  - One test each in core, api and web; `pnpm check` is green.
  - DB-test guard in the root `conftest.py`.

- 2026-09-25 **All six PLAN.md questions resolved** (Q1–Q6). ADR 0003 (secret storage), ADR 0004 (font substitution), ADR 0005 (drop React Flow), ADR 0006 (statistics methodology). PLAN.md §2, §3, §4, §5 updated to record the decisions; no more open questions block any phase.

## Next
- A1: CI workflow (`pnpm check` + integration/redis tests on service containers).
- A2: SQLAlchemy/psycopg/Alembic + settings. After that, `pnpm db:migrate` works.
- B1.1: suite YAML schema — first task that needs the statistics config surface from ADR 0006 (`statistics:` block) plumbed through.

## Decisions
- The user approved PLAN.md §2 items 1–6 and 8 (immutable case rows, ingest/baseline endpoints, same-origin cookie auth, signup allowlist + budget guard, case-level judgments, share links, separate judge cost).
- TypeScript 5.9 / ESLint 9 instead of 7 / 10 ([ADR 0002](decisions/0002-web-toolchain-versions.md)).
- `agents.secret_ref` references a new `secrets` table, Fernet-encrypted, write-only ([ADR 0003](decisions/0003-secret-storage.md)). Unblocks B2.1.
- Display font: Geist; monospace: Geist Mono; body: Inter Variable (unchanged) ([ADR 0004](decisions/0004-font-substitution.md)).
- Trace timeline: plain HTML/CSS, no React Flow ([ADR 0005](decisions/0005-trace-timeline-no-react-flow.md)).
- Regression statistics: Fisher exact + Holm (per case), paired sign-flip permutation (suite), case-level bootstrap CI; α=0.05, min_drop=0.05, all configurable via suite YAML and CLI flags ([ADR 0006](decisions/0006-statistics-methodology.md)).
- Hosting for the API/worker (Q2) is deliberately deferred to Phase F4; the only binding constraint now is that the worker stays behind the `QueueBackend` interface with `inline` as the local default.
- `packages/core` must contain exactly one run-execution implementation (`execute_attempt` / `finalize_run` / `run_suite`), shared by the CLI's local run and the server runner — no duplicate run loops (Q6 requirement, tracked at B1.7).

## Known issues
- `pnpm db:migrate` fails until A2 adds Alembic and `apps/api/alembic.ini`.
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1`. Without them it refuses with exit code 2, which is intended.
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed.
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
