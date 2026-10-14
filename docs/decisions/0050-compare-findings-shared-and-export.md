# 0050: Compare, findings, the public snapshot, attempt detail and the HTML export

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md), [ADR 0048](0048-overview-agents-and-suites-pages.md) and [ADR 0049](0049-runs-run-board-and-trace-viewer.md). Replaces the page-level parts of [ADR 0031](0031-run-detail-and-trace-viewer.md) for the compare and findings pages; the data rules of [ADR 0014](0014-statistics-implementation.md), [ADR 0018](0018-results-api-and-export.md) and [ADR 0024](0024-failure-clustering.md) stand.

## Context
The compare page, the findings page, the public `/shared/[token]` page and the per-case attempt detail still ran on the legacy alias names. The brief asked for charts in the telemetry style (mono axis labels, 1px strokes, flat fills, lime for the candidate or pass, plain ink or grey for a baseline, red only for failure, no colour fade, no animation beyond a short stepped draw-in that reduced motion turns off, direct labels, a table alternative), a compare verdict stated as one bordered sentence built from real values, a public page that looks complete and standalone with a "READ-ONLY SNAPSHOT" strip and every security property kept, and an HTML export that matches the look and stays self-contained.

## Decision

### 1. Lime in a chart marks the candidate; status marks are unchanged
DESIGN.md says lime is never a pass colour and a solid lime fill means two things. The brief asks for lime on the candidate and on pass in charts. Both hold if "pass" in a chart means the series under examination: in a chart, lime marks the **candidate** (the run being judged; on the public page, the one run it shows), and it appears as a stroke, a marker, a bar or an attempt square. Status chips, table cells and the "Pass" badge keep ink (DESIGN.md Status encoding); a baseline is ink; red is failure and nothing else; a flaky bar is hatched. DESIGN.md gains a "Charts" section stating this, so the exception has one source.

### 2. The charts are HTML and CSS, laid out in percentages
`components/ui/telemetry`: `RateWhiskers` (a rate and its 95% interval on a fixed 0 to 100% ruler), `AttemptStrip` (one shape per attempt: filled square, knocked-out cross, hollow `!`), `Bars` (one scale, value written on the row, hatch for flaky), `RunTrend` (pass rate by run, a 1px line the only SVG), `ChartFigure` and `ChartTable`. Labels are real mono type at any width, selectable, never scaled with a viewBox; at 390px they are the same 10 to 13px as at 1440. No legend: every row names itself. Every figure carries a `<details>` "Table view" with the plotted values as text, so the figure is not the only form of its data. Strokes are 1px and fills flat; the only animation is `draw-in`, a clip revealed left to right in six hard steps over 400ms, gone under `prefers-reduced-motion` and the dev switch.

### 3. No statistic is computed in the browser
Interval whiskers use the intervals the API stores for each run (`ci_lower`/`ci_upper`, core's bootstrap). A per-case Wilson interval is not in the report's dump, and re-implementing it in the web layer would put a second copy of a statistic where core's label rule was deliberately kept single (`regression.ts`). Per-case rows therefore show counts as attempt marks, not a per-case interval. Adding `wilson` to core's `CaseSummary` dump is the way to add it later; it would change the shape CLI runs and the Action's fixtures carry, so it is a decision for its own change.

### 4. The verdict sentence says "corrected threshold"
`verdictLine(report)` returns the word and the numbers that decided it: `Regression: refund-outside-window, p=0.0040, corrected threshold=0.0125, +1 more case`; a suite-level verdict states the paired test (`suite pass rate −20.0 pts, p=0.0123 vs α_suite=0.025`); no change states how many cases were compared and the lowest p. The brief's example reads "corrected p"; ADR 0014 has no adjusted p-values (the Tarone–Holm step-down yields a threshold each p must meet), and ADR 0049 §5 already says so on the run page. The sentence uses the threshold. It sits in one 1px bordered box (red for regression, lime for improvement, ink for no change, with the verdict word as DESIGN.md's verdict chip), and the prose that explains the test stays under it. The case id inside it is verbatim.

### 5. One attempt detail for the run page, the findings page and the snapshot
`AttemptList` shows an attempt's number, outcome, readouts, the agent's output and each judge's reason, with a red left edge for a failure. The run page's case rows, the findings' members and the public page's rows all use it. Output and reasons go through `PlainText` (text children only, control and bidi characters made visible). A public snapshot passes no trace link and no latency or cost.

### 6. The public page is standalone
A strip under the header reads `[ READ-ONLY SNAPSHOT ]`, the capture time and what is left out (agent config, credentials, raw traces). Then the suite name verbatim, the totals, the pass rate with its interval, the cases by stability and the expandable cases. Its links are the wordmark and "Try AgentProbe" only. The CSP is the one `proxy.ts` already sets for `/shared/*`; no response header changed. `BareHeader` can drop the API chip below 810px (`chipFromTablet`), because the wordmark, the chip and the button do not fit at 390px; the page has its data by then.

### 7. The HTML export keeps its tag allowlist
The export is restyled to the same look with the tags the XSS regression already allowed: spans positioned in percentages for the whisker, marks and bars, tables for layout, no `<div>`, `<svg>`, image, link or font file. It sets no font URL: the named families are used if installed, system fonts otherwise. The page's CSP stays `default-src 'none'; style-src 'unsafe-inline'`, so even a `data:` URI would be blocked; the flaky hatch is a hard-stop repeating gradient in CSS for that reason (an SVG mask, as the app uses, would need `img-src`). Below 700px a wide table scrolls inside its own box.

## Consequences
- The compare page fetches one list of the suite's completed runs for both the picker and the trend, so a run older than the newest 50 is absent from the trend (the figure says "Newest 50 runs").
- Per-case whiskers wait on `wilson` being in core's dump (§3).
- Spec 06 and its page object now look for "Read-only snapshot" where they looked for "Shared run · read-only".
- The legacy aliases (`Card`, `GradientCard`, the `chart-*` colours and the old type names) are no longer used by any page; removing them touches the theme and the design boards and is left for its own change.
- The existing Recharts trend charts on the overview keep their ADR 0028 rules (ink, dashed baseline); they were not part of this change.
