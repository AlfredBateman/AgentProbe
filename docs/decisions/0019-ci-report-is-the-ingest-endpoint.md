# 0019: `/ci/report` is the single run-ingest endpoint, and returns data only

Status: accepted (2026-09-26). Amends PLAN.md §2 #2.

## Context
PLAN.md §2 #2 planned two endpoints for runs executed outside the server: `POST /projects/{id}/runs:ingest` to store a locally executed run, and `POST /ci/report` to return a verdict plus ready-made PR-comment markdown. B2.5 ([ADR 0018](0018-results-compare-ci-report-export-share.md)) built only `/ci/report`, which stores the run *and* compares it with a baseline, and returned no markdown. Neither choice was recorded.

## Decision
- **`POST /ci/report` is the only way to ingest a run.** `runs:ingest` is intentionally not built. Storing a run and comparing it with its baseline are one step for every caller (the CLI's `run --push`, the GitHub Action): a caller that doesn't care about the verdict ignores it, and `verdict` is `no_baseline` when there's nothing to compare with. A second endpoint would duplicate the validation (`check_results`) and persistence, with nothing only it could do.
- **`/ci/report` returns structured data only**: `run_id`, `verdict`, the full `comparison` (core's `RegressionReport`), `top_findings` (empty until C4) and `dashboard_url`. The GitHub Action (F1) formats the PR comment from that JSON and posts it itself with `GITHUB_TOKEN`, so the API never holds GitHub tokens (unchanged from PLAN.md) and never renders Markdown from untrusted text.

## Consequences
- The comment's wording and layout live with the Action and change without an API release. Other consumers (the CLI's terminal output, a future Slack notifier) format the same JSON their own way.
- Case ids in the comparison, and suite and agent names, are user-supplied text. The Action, as the renderer, must escape them for Markdown; that belongs in F1's tests.
- Anyone reading PLAN.md's original B2.5 row should follow the amendment there to this ADR.
