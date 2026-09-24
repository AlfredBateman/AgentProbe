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

## Next
- Answer the open questions in [PLAN.md §5](PLAN.md#5-questions-for-you). Q1 blocks B2.1.
- A1: CI workflow (`pnpm check` + integration/redis tests on service containers).
- A2: SQLAlchemy/psycopg/Alembic + settings. After that, `pnpm db:migrate` works.

## Decisions
- The user approved PLAN.md §2 items 1–6 and 8 (immutable case rows, ingest/baseline endpoints, same-origin cookie auth, signup allowlist + budget guard, case-level judgments, share links, separate judge cost).
- Item 7 (`agents.secret_ref`) stays as SPEC wrote it; its meaning is open (Q1).
- TypeScript 5.9 / ESLint 9 instead of 7 / 10 ([ADR 0002](decisions/0002-web-toolchain-versions.md)).

## Known issues
- `pnpm db:migrate` fails until A2 adds Alembic and `apps/api/alembic.ini`.
- `pnpm verify` needs `TEST_DATABASE_URL`, `DATABASE_URL` and `ALLOW_DB_TESTS=1`. Without them it refuses with exit code 2, which is intended.
- The pytest run shows a `StarletteDeprecationWarning`: Starlette's TestClient wants `httpx2` instead of `httpx`. Swapping `httpx==0.28.1` for `httpx2` was blocked by a local permission rule this session. Redo it once allowed.
- `next build` downloads Google Fonts (Inter, Geist), so it needs network access. `pnpm check` doesn't build.
