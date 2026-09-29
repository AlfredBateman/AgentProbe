# 0032: GitHub Action design, PR comment escaping, and the dogfood workflow's baseline

Status: accepted (2026-09-29). Completes PLAN.md F1 and F2.

## Context
F1 needed a reusable composite GitHub Action that runs an AgentProbe suite, gates a PR's
required check on the CLI's own exit code, and posts a PR comment. F2 needed AgentProbe's own
CI to dogfood that action against `demo-agents/` and `suites/examples/`, comparing each PR's
run against "the result from main." No AgentProbe server is deployed yet (PLAN.md F4 is not
started), so `--push`'s server-side baseline (ADR 0018/0020) has nothing to compare against in
this repo's own CI today, even though the action must support it for anyone who *has* deployed
a server.

## Decision

### The action supports both a server baseline and a local one, and a caller picks one
`action/action.yml` takes optional `api-url`/`api-key` (server mode: `agentprobe run --push`,
comparing against that branch's server-side baseline) and an optional `baseline-run` (a path to
a local run JSON file, compared with `agentprobe run --baseline`). Exactly one of these applies
per run — server mode wins when both a key and URL are present, since a deployed server's
baseline is authoritative once one exists (ADR 0020). Neither implies the other is wrong: a
user without a deployed server still gets local regression detection from a baseline file their
own workflow supplies; PLAN.md F4 later makes server mode the default without changing the
action's contract.

### The dogfood workflow's baseline is a workflow artifact, not a server push
`.github/workflows/agentprobe-dogfood.yml` runs a `baseline` job on every push to `main` that
touches `demo-agents/**` or `suites/**`: it starts the demo agents, runs each example suite
through the action with no `api-key` (so it runs local/mock, no push), and uploads the raw
`agentprobe run --json` result as a workflow artifact per suite
(`dogfood-baseline-<suite>-<agent>`). A `dogfood` job on pull requests touching the same paths
downloads the latest such artifact from the most recent successful run of this same workflow on
`main` (via `gh run list --workflow=... --branch=main --status=success` +
`gh run download <run-id>`, both preinstalled on GitHub-hosted runners — no third-party
download-artifact action needed for a cross-run fetch) and passes it to the action's
`baseline-run` input. This is explicitly a placeholder for the server-side baseline: once F4
deploys a server, the dogfood workflow switches to `api-url`/`api-key` (already supported by the
action) and the artifact dance goes away. Until then, an artifact is simpler than standing up
infrastructure just to test infrastructure, and "most robust" mostly means: if `gh run download`
finds nothing (first run ever, or `main`'s last run never uploaded a baseline for this suite),
the action runs with no baseline at all rather than failing — a missing baseline is not an
error, per `agentprobe run`'s own semantics.

### PR comment: one comment per suite+agent, upserted by a hidden marker
Each matrix job posts or updates its own PR comment (`format_comment.MARKER`, a fixed HTML
comment) rather than one job aggregating all suites into a single comment, because a composite
action step can't easily merge results across parallel matrix jobs without a second workaround
(an artifact or an issue-comment read-modify-write race). `post_comment.py` searches existing
issue comments for one starting with the marker and PATCHes it; job re-runs update in place
instead of piling up duplicate comments. This means a PR touching multiple suites gets multiple
AgentProbe comments (one per suite/agent pair) — acceptable, and each is clearly titled.

### Escaping untrusted text in the comment (ADR 0019's requirement)
Suite/agent/branch names and case ids are wrapped in Markdown code spans, whose content is
never re-parsed as Markdown; the only character that matters there is a literal backtick, which
`format_comment.code_span` replaces with `'` (and flattens embedded newlines, which would
otherwise split a code span across lines). LLM-generated cluster labels/summaries/suggested
fixes (`top_findings`, C4/ADR 0024) are prose, not identifiers, so they go through
`format_comment.escape_md` instead, which backslash-escapes CommonMark's ASCII punctuation.
`action/tests/test_format_comment.py` fixtures include a finding summary with literal
`*outside*` and a suite name crafted as `evil](javascript:x)`, asserting neither reopens
Markdown syntax in the rendered comment.

### Fork PRs degrade gracefully at two independent points
Fork PRs never receive repository secrets, so `api-key` arrives empty; the action's run step
already treats a missing key/URL as "run local/mock, no push" and emits an `::notice::` saying
so — not a failure. Separately, a fork PR's `GITHUB_TOKEN` is read-only and can't create or
update issue comments even when the caller passes one; `post_comment.py` catches the resulting
403/404 as an `HTTPError`, prints an `::warning::`, and exits 0 rather than failing the step.
Neither degradation touches the actual gate: the final step re-exits with `agentprobe run`'s own
exit code, so a fork PR with a genuine regression still fails its required check even though
nobody could comment on it.

### Amendment (2026-09-29): per-suite `fail-under`, not a blanket 1.0
The dogfood workflow's first real run on `main` failed two of its three matrix jobs. Neither
was a bug in the action: `smoke.yaml`'s `order-status` case is seeded ~20%-flaky per attempt
(`demo-agents/README.md`), so its suite pass rate is routinely below the action's default
`fail-under: "1.0"`; `rag-safety.yaml`'s `rag-indirect-injection` case failed **every** run,
confirmed locally by running it directly — the `rag` demo agent has no retrieved-content
filtering at all (`vulnerabilities.json`), so that case can never pass against it, seeded or
not. Gating a required check on 100% for a suite with a known, permanently-reproducible planted
vulnerability would make the check permanently red, which is worse than no check. Each matrix
entry now carries its own `fail-under` matching that suite's real, currently-accepted ceiling
(smoke 0.9, tolerating the flaky case; rag-safety 0.5, tolerating the one known-failing case;
support-agent-safety stays at 1.0, since it already passes cleanly against `support-v1`) rather
than a single blanket value. This is a floor under today's known state, not a substitute for
regression detection: a case that gets worse than its own documented ceiling still drops the
suite below its floor and fails the check.

Separately, "Save this run as the next PR's baseline" is now `if: always()`, not merely
`if: github.event_name == 'push'`: the baseline artifact must be uploaded whether or not that
run's own `fail-under` check passed, since the baseline is defined as "whatever `main` currently
produces," not "whatever `main` produces on the runs that happen to pass." The prior code that
had no `always()` guard was untested until this first real push, and would have skipped the
upload silently on the very runs (smoke, rag-safety) that most needed one recorded.

## Consequences
- The dogfood workflow's artifact-based baseline is intentionally throwaway: it has no
  versioning, retention policy beyond GitHub's default (90 days on public repos), and no
  protection against `main`'s last run itself having been a regression that never got caught
  (there's no server-side `POST /projects/{id}/baseline` gate on it, ADR 0018). Revisit once F4
  ships a server: point the dogfood workflow at `api-url`/`api-key` and delete the artifact
  plumbing.
- A PR that touches `demo-agents/**`/`suites/**` gets one comment per suite in the dogfood
  matrix; a future improvement could have one job collect every matrix job's JSON result (via
  artifacts) and post a single combined comment, but nothing in the pitch (POSITIONING.md)
  needs that now.
- `action/action.yml` is otherwise generic and untied to this repo: any project can point
  `suite`/`config` at its own files and use `api-url`/`api-key` alone, with `baseline-run` and
  the workflow-artifact dance being this repo's own dogfood concern, not a documented feature
  of the action itself beyond the input existing.
