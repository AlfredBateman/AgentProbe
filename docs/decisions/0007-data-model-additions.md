# 0007: Data model additions and conventions

Status: accepted (2026-09-25)

## Context
SPEC.md §7 lists the tables but not the columns needed to reproduce a run, report it per case, share it, or keep an agent's secret. PLAN.md §3 already approved some changes: versioned immutable cases, judgment scopes, `judge_cost_usd`, `share_token_hash`, and the `secrets` table from ADR 0003. Phase A3 needed the rest pinned down before the first migration.

## Decision
Additions requested in the A1–A3 task:
- **runs**:
  - `config_snapshot` JSONB: the suite YAML and agent config captured at run start, so a run can be reproduced after either is edited.
  - `error` text.
  - `mock_mode` bool.
  - `pr_number`.
  - `share_token_hash`: nullable, unique. It holds the SHA-256 of the share token, never the token itself (user decision, PLAN §2 #6), so a database leak exposes no working links.
  - `share_expires_at`.
  - `created_at`.
- **run_results**: unique (run_id, case_id, attempt).
- **run_case_summaries**:
  - Columns: `run_id`, `case_id`, `attempts`, `passes`, `pass_rate`, `label`, `mean_score`, `consistency_score`, `mean_latency_ms`, `total_cost`.
  - PK (run_id, case_id).
  - CHECK on `label` (`stable-pass | stable-fail | flaky`) and on `0 ≤ passes ≤ attempts`.
- **secrets**: `id`, `project_id`, `ciphertext` (bytea, Fernet), `created_at`. `agents.secret_ref` is an FK with ON DELETE SET NULL (ADR 0003).
- **findings.embedding** is `vector(EMBEDDING_DIM)`. The migration reads the dimension from config when it runs, so changing `EMBEDDING_DIM` afterwards needs a new migration. The drift test catches a mismatch.
- **Indexes**:
  - Every foreign key is covered by an index that *leads with* its column. Where a composite unique or PK index already leads with the FK (for example `run_results (run_id, …)`), no duplicate index is added. `test_migrations.py` asserts the rule against the catalog.
  - Plus `ix_runs_suite_id_created_at (suite_id, created_at)`.

Conventions:
- **UUID primary keys**, generated in Python (`uuid4`). Run and result ids appear in URLs, so they shouldn't be enumerable.
- **Status and label columns are text + CHECK**, not PG enums. Adding a value is then a one-line constraint swap, not `ALTER TYPE`.
- **Money is `NUMERIC(12,6)`**: exact, and sub-cent LLM costs are representable.
- **`timestamptz` everywhere**, with `server_default now()` on `created_at`.
- **Deletes CASCADE along ownership** (user → project → agents/suites/secrets/keys/baselines; suite/agent → runs → results → traces/judgments). The exception is `secret_ref`, which is SET NULL.
- **Unique (project_id, name)** on `agents` and `suites`, because ingest upserts both by name (PLAN §2 #2).
- **Deterministic constraint names** via a SQLAlchemy naming convention (`pk_`, `fk_`, `uq_`, `ck_`, `ix_`), so later migrations can reference them.

## Consequences
- Deleting an agent or suite deletes its run history. Acceptable for v1; soft-delete can come later if it's ever needed.
- Changing the embedding model's dimension is a schema migration, not a config flip.
- `tests/test_migrations.py` enforces model/migration drift and FK index coverage, so later migrations can't silently break either.
