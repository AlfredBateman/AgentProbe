# 0003: Agent secrets live in a separate `secrets` table

Status: accepted (2026-09-25)

## Context
SPEC.md §7 gives `agents` a `secret_ref` column (for the HTTP adapter's auth header) but never says what it references. Two options were on the table: an inline encrypted column on `agents` itself, or a separate table of encrypted values with `secret_ref` as a foreign id. The user chose the latter, so that `secret_ref` stays a genuine reference rather than a misnamed inline column.

## Decision
Add a `secrets` table:
- `id` (referenced by `agents.secret_ref`)
- `project_id`
- `ciphertext` (Fernet, key from the `ENCRYPTION_KEY` env var)
- `created_at`

Secrets are written through a dedicated API path, never returned in any response body, and never logged. `agents.secret_ref` keeps its name from SPEC.md and now resolves to this table's `id`. Key rotation via `MultiFernet` is deferred until it's needed.

## Consequences
- Deleting a secret is a real delete on its own row, independent of the `agents` row lifecycle.
- One decryption path (used by the HTTP adapter when it builds the outgoing request) instead of ad hoc column access on `agents`.
- Implemented in Phase B2.1.
