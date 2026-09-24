# AgentProbe

## Database

AgentProbe uses Postgres with pgvector. Locally that's Neon branches: one for development (`DATABASE_URL`) and a separate one for integration tests (`TEST_DATABASE_URL`).

The expected format (psycopg 3 driver, TLS):

```
postgresql+psycopg://USER:PASSWORD@ep-XXXX-XXXX.REGION.aws.neon.tech/DBNAME?sslmode=require&channel_binding=require
```

Converting the connection string Neon gives you (Dashboard → Connect):
- Neon shows `postgresql://USER:PASSWORD@ep-…neon.tech/DBNAME?sslmode=require&channel_binding=require`.
- You can paste it **as-is**. The app rewrites `postgresql://` (or `postgres://`) to `postgresql+psycopg://`. You can also change the scheme yourself.
- Keep `sslmode=require` and `channel_binding=require`. If a remote URL has no `sslmode`, the app adds `sslmode=require`.
- Use the **direct** host, the one without `-pooler` in its name.
- `TEST_DATABASE_URL` must point at a different branch than `DATABASE_URL`. Integration tests also refuse to run unless `ALLOW_DB_TESTS=1`.

Commands:
- `pnpm db:migrate`: apply migrations to `DATABASE_URL`.
- `pnpm verify`: `pnpm check`, then integration tests on `TEST_DATABASE_URL`.

Both load `.env`. The first connection after Neon has been idle can take a few seconds while the compute wakes up.
