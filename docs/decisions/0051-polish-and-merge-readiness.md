# 0051: Polish and merge readiness for the UI overhaul

Status: accepted (2026-10-14). Amends [ADR 0042](0042-industrial-brutalist-design-system.md) (the noise layer, the alias names), [ADR 0048](0048-overview-agents-and-suites-pages.md) (the overview's trends) and [ADR 0050](0050-compare-findings-shared-and-export.md) §7 (the export's flaky hatch). The clustering rules of [ADR 0024](0024-failure-clustering.md) stand.

## Context
The last review of the `ui-overhaul` branch found unreadable mock findings, findings pages that listed every identical attempt, tables that clipped at 390px with no sign they scrolled, dead space on the compare page, an overview that drew an empty cost chart and a confidence band over two points, legacy alias names still generated, and an e2e suite that failed against a slow Neon test branch. The brief also asked for a whole-app pass: every route at three widths, axe, keyboard use, the noise and scanline layers checked against AA, performance numbers and dead-code removal.

## Decision

### 1. The mock summarizer describes a cluster from its facts
The mock provider's summarizer answer is a hash of its prompt, so mock findings read "mock summarizer response 76c4…" twice. `cluster_failures` now takes `FailingOutput(result_id, text, case_key, failed_judges)`. When the client's provider is the mock, each cluster is described by `describe_locally`: the label is "10 attempts failed tool_not_called: issue_refund on refund-outside-window". The summary, shown under the label, does not repeat it: it gives an 80-character excerpt of the output ("All 10 gave the same output: …" when they match) and lists the cases when there are several. The fix joins the advice for the two most telling failing judges, ranked so an action outranks wording (a tool call before `contains_any`), and names the tool ("Stop the agent calling issue_refund here: …"). No LLM call is made for it. Live clients still get the same prompt with outputs only, and the same parsing; the metadata never enters a prompt. The API builds `failed_judges` from each attempt's verdicts, lined up with the case's non-consistency judges to name a tool judge's tool.

### 2. Findings fold identical outputs
A finding's members start collapsed behind "Show N members". Inside, attempts whose output is byte-identical are one row, "10 attempts, identical output", with the output shown once and a "Show the 10 attempts" control that opens the usual attempt detail. Output stays `PlainText`.

### 3. Wide tables are labelled scroll regions with a hint
`ScrollRegion` wraps every table that can be wider than its panel (`DataTable`, the per-case tests, every chart's table view). While its content overflows, it is a focusable `role="region"` named "<caption>, scrolls sideways", with a strip above it saying "Scroll sideways" and an arrow toward whichever side still has columns. When the table fits, it is a plain box with no tab stop. Stacking rows into cards was rejected: the tables are comparisons, and a column read down is the point.

### 4. Compare: equal chart heights, a full-width odd panel, a one-line key
The two figures stretch to one row height, with their table views on the same line. Transition panels render only when they have cases, and an odd one out spans the row. A one-line key over the charts says that on this page lime is the candidate, white the baseline and red a failed attempt, because the attempt strips in the cases table use lime for the candidate's passes (ADR 0050 §1). DESIGN.md's "Direct labels, no legend" still holds for each chart. The key covers the page's one colour exception.

### 5. Overview trends follow the chart rules
The Recharts trends now use 1px strokes, mono ticks, square markers and flat fills. A second series is dashed ink-muted, not a `chart-2` grey. Below three runs every point has its marker and the CI band and its legend key are left out. With no cost recorded, "Cost per run" is one line of text, and latency takes the full row. The Run buttons on the overview show their disabled reason as text.

### 6. No alias names
DESIGN.md's `aliases` block is gone (status names, `primary`, `chart-1..4`, the old type tiers), and so are `Card`, `GradientCard`, the `translucent` button variant, `--font-display` and the two `--shadow-*` variables. `theme.test.ts` fails if `aliases` comes back. One name means one value.

### 7. The grain sits behind the content
The noise tile's lightest pixels were measured in Chromium at 0.718 (premultiplied) and its darkest at 0.360. At 4.5% opacity over text, that takes `fail` on `surface-2` from 4.65:1 to 4.16:1. No visible strength keeps that pair at AA, because it starts 0.15 above the line. `zIndex.noise` is now −1. The grain textures the page canvas between panels and never covers a glyph. The optional page-wide scanlines use the same layer. The hero's in-box "Illustrative" tag sits above its figure's scanlines.

### 8. The export's flaky bar is a dashed outline
The export's CSP is `default-src 'none'`, so it can't use the SVG mask the app hatches with. ADR 0050 §7 used a hard-stop repeating gradient instead. The brief asks that a search for "gradient" finds nothing, so the export draws the flaky bar as a 1px dashed ink outline, the flaky chip's edge. The bar still doesn't depend on colour.

### 9. An attempt save holds the run lock for its last two round trips
`save_attempt` locked the run row first (`SELECT … FOR UPDATE`), then inserted the result, trace and judgments, updated the counter and committed. That is about six round trips under the lock, and all of a run's attempts serialize on it. On the Neon test branch at 200ms that is about 1.2s per attempt, over 60s for a 45-attempt run, which is the root of the e2e failures (05 and 06 timing out, their unfinished runs crashing when `afterAll` deleted the account, later specs slowing behind them). The save now inserts first, without the lock, and ends with `UPDATE runs … WHERE status = 'running' RETURNING attempts_done`. Only that statement and the commit hold the lock. Postgres re-checks the `WHERE` after waiting on a cancel's lock, so a late attempt matches nothing and the whole attempt is rolled back, and a redelivered attempt still conflicts and keeps nothing. The behaviour is the same with a third of the time under the lock.

### 10. Clustering computes each distance once
`pnpm verify` failed twice on the golden API test. The run's clustering job sat idle in its database transaction for over five minutes, and Postgres killed it (`idle_in_transaction_session_timeout` is 5min on the Neon branch). `agglomerative_cluster` recomputed every member-pair cosine distance on every merge, which is O(n^4 · dim) pure-Python work. For the vulnerable bot's 50 failing outputs that was seconds untraced and minutes under coverage's line tracing (the same test took 185s on 2026-10-13, so the margin was already thin). The function now computes each pair once and merges on that matrix (single linkage: a merged cluster's distance to another is the smaller of its parts'). The result is the same: a seeded property test compares it with the recomputing definition, ties included, and a test pins the cost at n(n−1)/2 distance calls. The golden test takes 59s under coverage. The clustering job still holds the caller's transaction while it computes; for `/ci/report` that is deliberate (one transaction for the ingest).

## Consequences
- Mock findings are readable and stable across runs. A live summary that comes back unformatted still falls back as before.
- `scripts/measure_clustering.py` passes the case and failing judges too; the mock rows it writes to docs/metrics.md will change when it is next run.
- `e2e/19-whole-app.spec.ts` walks every route at 1440, 810 and 390px (touch at 390) for overflow, clipped headers and headings, serious or critical axe findings, and 44px tap targets, and checks keyboard use of the shell, a dialog, a sortable header and the trace viewer, with the 2px lime ring on every stop. `@axe-core/playwright@4.13.0` is a new dev dependency of `apps/web`.
- The grain no longer shows over panels, only in the gutters and around them.
