# 0008: Database connection config and integration-test isolation

Status: accepted (2026-09-25)

## Context
Locally, the database is Neon: remote, TLS-only, and it suspends compute after about 5 minutes idle, so the first connection after a pause cold-starts. `pnpm verify` runs integration tests over that network link. CI can't use Neon (no secrets in forks, and it would be slow), and the user can't run Docker locally.

## Decision
**Driver and URL.**
- psycopg 3 (`postgresql+psycopg://`). asyncpg rejects Neon's `sslmode`/`channel_binding` params (PLAN §2 #18).
- `db.normalize_url` accepts the `postgresql://…` string Neon gives you and rewrites the scheme.
- It adds `sslmode=require` to any non-local URL that doesn't set one, so TLS is the default and never an opt-in. Neon's own params pass through to libpq.

**Engine.**
- `pool_pre_ping=True`: a suspended compute has closed our pooled sockets.
- `pool_recycle=300`: matches Neon's idle suspend.
- `connect_timeout=10`: covers a cold start but fails rather than hangs.
- Tests build their engine with the same `make_engine`, so `verify` exercises this config.

**Migrations run synchronously.**
- psycopg 3 serves both sync and async from the same URL, and DDL gains nothing from an event loop.
- `env.py` takes the URL from `config.attributes["url"]` (tests) or `DATABASE_URL`, and never from `alembic.ini`.

**Test isolation: rollback per test on one session-wide connection.**
- A session fixture migrates the test branch to head once.
- Each test gets a connection with an open outer transaction. Its `AsyncSession` joins with `join_transaction_mode="create_savepoint"`, and the outer transaction is rolled back afterwards.
- Why rollback wins over a network link:
  - The per-test cost is one `BEGIN` and one `ROLLBACK` on an already-open TLS connection: no DDL, no reconnect.
  - `TRUNCATE` of every table costs a round-trip plus an ACCESS EXCLUSIVE lock per test, and grows with the table count.
  - A schema or database per test costs seconds of DDL or migration per test.
- Code under test can still `commit()`, because the commit releases a savepoint. Constraint-violation tests wrap the failing flush in `begin_nested()`.
- The pytest-asyncio loop is session-scoped so that one connection can serve every test.

**Windows.**
- psycopg's async mode can't use the default ProactorEventLoop.
- The root conftest implements `pytest_asyncio_loop_factories` on `win32` to use `SelectorEventLoop`.
- Migrations need no loop because they are sync.

**CI** uses service containers instead of Neon:
- `pgvector/pgvector:0.8.6-pg18`, the same Postgres major (18) and pgvector version as the Neon branches;
- `redis:8-alpine`.

The same `pytest -m "not live"` then runs unit, integration and `redis` tests against real services. (Since ADR 0017, `redis` tests run in their own verbose step: `pytest -m "not live and not redis"`, then `pytest -m redis -v -rA`.)

**Guard.** The root conftest compares the (host, port, database) of `TEST_DATABASE_URL` and `DATABASE_URL`, not the raw strings. `postgresql://X` and `postgresql+psycopg://X` are the same database. `test_db_guard.py` proves every refusal path via pytester.

## Consequences
- A test that needs to observe a truly committed transaction from a second connection can't use the `db` fixture. None does yet.
- The migration round-trip test drops and recreates the schema mid-session. It's safe because the shared connection is idle between tests, but it ties the integration suite to one test database at a time.
- uvicorn on native Windows also needs the selector loop once the API opens DB connections. That's handled when A4 adds the first DB-backed endpoint.

## Amendment (2026-09-25, ADR 0017): background work in tests
Runs execute in the background (inline tasks, or worker jobs run in-process), each opening sessions through `app.state.sessionmaker`. `apitest.bind_db` replaces it with `SharedSessions`:
- every `sessions()` is the test's own savepoint session, so background writes still roll back with the test;
- one `asyncio.Lock` is shared with the per-request session, so a request and a worker never use the connection at the same time;
- each block ends with a rollback, as closing a real session would, so a missing commit fails in tests as it would in production.

The worker is never a separate process in tests, because it couldn't see the test's transaction.
