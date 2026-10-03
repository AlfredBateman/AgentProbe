# 0034: Dependency audits in CI, and how a finding is handled

Status: accepted (2026-09-29). Part of PLAN.md F5 (dependency audit), done alongside F3.

## Context
CI had no check for dependencies with known vulnerabilities. Both ecosystems are exactly pinned
and locked (`uv.lock`, `pnpm-lock.yaml`), so what an audit has to answer is whether anything
in those lockfiles has a published advisory.

## Decision
- CI's `audit` job runs two audits. For Python, `uv export --locked --all-extras --all-groups
  --no-emit-workspace` feeds `pip-audit==2.10.1 --disable-pip`. That audits the hashed,
  pinned export as-is, without re-resolving it. For npm, `pnpm audit` audits the whole
  lockfile.
- The scope is everything locked: the dev tools and the `live` extra (LiteLLM), not just what
  ships in an image. Dev tools run in CI with repository access.
- Any finding at any severity fails the job. There's no severity threshold, so a new advisory
  gets looked at rather than scrolled past.
- A finding is handled in this order:
  1. **Fix**: upgrade to a patched version (exact pin, lockfile updated).
  2. **Pin**: if the patched version is blocked, pin or override the transitive dependency
     to a safe version (`[tool.uv] constraint-dependencies`, or pnpm `overrides`).
  3. **Accept**: if neither is possible or the vulnerable code isn't reachable, add the
     advisory ID to the ignore list: `pip-audit --ignore-vuln ID` in `ci.yml`, or
     `auditConfig.ignoreGhsas` in `pnpm-workspace.yaml`. Each accepted ID gets an entry below
     with its reason and when to look at it again.
- The first run (2026-09-29) found nothing. `pip-audit` covered 113 packages with 0 skipped;
  `pnpm audit` was clean.

## Accepted risks
- **GHSA-vfj7-8cjw-p6xm, `braces` <= 3.0.3** (high: stack exhaustion on deeply nested brace
  patterns). Accepted 2026-10-03, when CI first flagged it. No patched release exists: npm's
  latest is 3.0.3, and the advisory names no fixed version, so neither fixing nor pinning is
  possible. Reachable only through ESLint (`eslint-config-next` > `@next/eslint-plugin-next` >
  `fast-glob` > `micromatch`), a dev dependency that expands this repo's own glob patterns. It
  never sees user input and isn't in the production bundle. Look again when `braces` 3.0.4 or
  a fixed `micromatch` is released, then remove the ignore in `pnpm-workspace.yaml`.

## Consequences
- An advisory published upstream can turn CI red on a commit that changed nothing. That's
  deliberate: the job exists to surface new advisories.
- The audits need network access to the PyPI and npm advisory databases, so this is a CI job,
  not part of the offline `pnpm check`.
- OS packages inside the Docker images aren't audited. An image scanner (for example Trivy)
  would cover them; add one when an image is deployed (F4).
