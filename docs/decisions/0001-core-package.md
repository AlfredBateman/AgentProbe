# 0001: Pure engine in packages/core

Status: accepted (2026-09-24)

## Context
SPEC.md §13 puts workers, adapters, judges and attacks inside `apps/api`. The CLI (`packages/cli`) has to run suites locally, both in the user's CI and on their machine, with no server. If it imported that logic from `apps/api`, it would pull in FastAPI, SQLAlchemy and a database dependency just to call an agent and score the output.

## Decision
Add `packages/core` (distribution `agentprobe-core`, module `agentprobe_core`). It holds the pure logic:
- suite schema
- adapters
- judges
- attacks
- statistics
- LLM layer
- single-attempt executor

It must not import a database or web framework. `apps/api` and `packages/cli` both depend on it. `apps/api` keeps persistence, HTTP routes, auth and the queue workers that wrap the core executor.

## Consequences
- The CLI installs without server dependencies; `pip install agentprobe` pulls in `agentprobe-core`.
- The engine is unit-testable offline, so `pnpm check` stays fast. mypy runs strict on it.
- Two packages have to be published to PyPI instead of one.
- The repository layout differs from SPEC.md §13.
