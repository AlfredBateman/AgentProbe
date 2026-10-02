# 0037: Project overview and the Runs page (E2)

Status: accepted (2026-10-03).

## Context
PLAN.md E2 and SPEC.md §9.3 ask for a project overview: a pass-rate trend, cost trend, latest runs. The user's brief added a confidence band on the pass rate, a latency trend, a baseline indicator and a "Run a suite" action, plus the page the nav's Runs link points to (it 404'd). ADR 0030 already added `GET /projects/{id}/runs` for this. The baseline indicator needed one thing the API didn't have: a way to list a project's baselines. The only read was `GET /projects/{id}/baselines/{branch}?suite=&agent=`, one key at a time.

## Decision
- **`GET /projects/{id}/baselines`** lists every baseline in the project as `BaselineOut` (branch, suite, agent, run id, and the run itself, so its pass rate comes along). It's owner-scoped like every other project route and is in the IDOR probe list. No new stored data.
- **One suite at a time.** Pass rates of different suites aren't comparable, so the trends show one suite, picked in a single filter row above the tiles and charts (default: the suite of the newest run). The latest-runs table below is project-wide and says so in its caption.
- **Charts** follow ADR 0028 §2 and the chart theme (`chart-theme.ts`):
  - pass rate: the run's point estimate as an ink line, its 95% CI (ADR 0006's case-level bootstrap, as stored on the run) as a faint ink band, and the suite's baseline (`main`'s if there is one) as a dashed ink-muted reference line;
  - cost: agent cost and judging cost as `chart-1`/`chart-2`, one y-axis (both USD);
  - latency: mean latency as an ink line;
  - the x-axis is runs in order (time of day when they all fall within a day, otherwise the date), not a time scale.

  Every chart has an HTML legend in text tokens. The runs table is the table view. A chart with nothing to draw says why instead of drawing empty axes. Cost counts as nothing when every value is zero or missing, which is what mock judging and an agent without a price produce.
- **Baseline indicator** in three places: a Baseline tile (its pass rate, a link to the run, the latest run's difference from it), the dashed line on the pass-rate chart, and a "Baseline · <branch>" badge on that run's row in both runs tables.
- **The Runs page** (`/projects/{id}/runs`) lists every run newest first, filters by suite on the server (`suite_id`), and pages with "Load more" (offset, deduplicated by id). The run page's breadcrumb now points at it.
- **"Run a suite"** is one dialog (`RunSuiteDialog`), shared with the Suites page (E3): suite, attempts per case (empty means the suite's own, 1–20), and an opt-in "Judge with the server's live LLM". Unticked is the mock judge, matching `RunIn`'s default and CLAUDE.md's "mock everywhere by default". The Suites page's old Run button sent `mock: false` unasked.
- **`DataTable` columns can carry a `className`.** The runs table uses `hidden desktop:table-cell` for cost and latency so the table fits its card at 810px (ADR 0028 §8). Agent is stacked under suite, and the CI under the pass rate, for the same reason.

## Consequences
- The overview reads the newest 200 runs (`ponytail:` in the page). A suite whose history goes further back shows only its last 200 in the trends.
- Below 1199px the runs tables omit cost and latency; the charts and the run page still show them.
- `GET /projects/{id}/baselines` returns each baseline's whole run. That's fine at the handful of baselines a project has (one per suite, branch and agent).
