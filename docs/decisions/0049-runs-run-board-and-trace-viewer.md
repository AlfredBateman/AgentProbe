# 0049: Runs list, live run board and trace viewer

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md), [ADR 0043](0043-ui-primitives-on-the-brutalist-system.md), [ADR 0044](0044-motion-layer.md) and [ADR 0048](0048-overview-agents-and-suites-pages.md). Replaces the page-level parts of [ADR 0031](0031-run-detail-and-trace-viewer.md) and [ADR 0037](0037-project-overview-and-runs-page.md) for these three pages; their data and streaming rules stand.

## Context
The runs list, a run's page and the trace viewer still ran on the legacy alias names. The brief asked for a dense runs table with status chips, filters, sort and pagination; a live board over the existing SSE stream (a segmented progress bar, a case grid whose cells change state with a short stepped flash that respects reduced motion, a statistics panel stating the verdict plainly, the failure clusters); and a trace viewer with collapsible steps, copy buttons and a judge-verdict panel, where trace text is text only and can influence nothing. The stream's reconnect, resync, polling fallback and cold-start behaviour were to stay as they are.

## Decision

### 1. The API filters, sorts and counts the runs list
`GET /projects/{id}/runs` gained `status`, `branch` (exact), `sort` (`created_at`, `pass_rate`, `cost`, `latency`, `suite`, `status`) and `order`, and returns the number of matching runs in `X-Total-Count`. All are optional and default to the old behaviour (newest first), so existing callers (the overview, the agents page, the trace picker) are unchanged. Unknown values sort last in either direction; ties keep newest first. Sorting or filtering one page in the browser would have sorted that page only, which reads as the whole list and isn't.

The page keeps its view in the URL (`?suite=&status=&branch=&sort=&order=&page=`, defaults left out), so a filtered view survives a reload and Back. 25 runs a page. `DataTable` gained a controlled sort (`sort`/`onSortChange`) for rows sorted elsewhere; on the Runs page only the columns the API can sort by are sortable. Run statuses now use their own marks (queued, running).

### 2. The board shows every case from the start
A run's cases come from `GET /suites/{id}/cases?version=` (the run's suite version, in YAML order), so a queued case has its cell before its first attempt; a case seen only in the attempts (an ingested run) is added after them. A cell is `queued`, `running` (some but not all attempts in), `pass`, `fail`, `flaky`, `error` (every attempt errored) or `not run` (a run that ended first). Before the run is summarized the state is read from the attempts; once it is, core's label decides (`stable-pass`, `flaky`, `stable-fail`), so the board never contradicts the cases table. A cell links to its first failing attempt's trace, or its first attempt.

### 3. The flash is a border clipped away in three steps
`useFlash` (lib/motion) shows a 2px border in the cell's colour and clips it away with `steps(3)` over 400ms when the cell's state changes. Never on mount (a finished board loads without every cell flashing), never under `prefers-reduced-motion` or the dev switch, through the same `gsap.matchMedia` context as the other hooks. A border, not a fill: a fast run changes many cells a second, and a thin outline keeps the changing area far below a flash hazard where a fill would not.

### 4. The progress bar is 40 segments with `role="progressbar"`
The native `<progress>` became a segmented bar (`aria-valuenow`/`max`/`text`), with the count in mono beside it. The stream hook (`useRunStream`) and its callbacks are unchanged; spec 04 reads `aria-valuenow` where it read `value`.

### 5. Statistics: corrected thresholds, not adjusted p-values
The panel states the run's own counts and pass-rate interval, then the verdict: the baseline's and this run's pass counts, the effect size in percentage points, the suite test's p in both directions against `α_suite`, and per case (flagged first, then by p, five shown) the counts, the difference, p and its corrected threshold. The brief asked for a corrected p-value; the per-case procedure (Tarone–Holm) has none that is well defined, which is why ADR 0014 reports thresholds. The panel says so in one sentence and shows the threshold each p had to meet, or "Not reached" where the step-down stopped. Every figure comes from the API's report; the page only sums counts.

### 6. Trace text is shown and copied inert
`visibleText` (components/ui/code) replaces C0/C1 control characters (ANSI and OSC sequences, an 8-bit CSI) and bidi controls with visible stand-ins (`␛`, `⟨U+202E⟩`) everywhere untrusted text is shown (`PlainText`, `CodeBlock`, the step's one-line preview and its subject). React already makes every string a text node; this closes the two ways text could still act on a reader: reordering itself on screen (Trojan Source) and restyling a terminal it is pasted into. Copy buttons put the same inert text on the clipboard. "Copy trace JSON" is lossless instead: `safeJson` escapes the characters `JSON.stringify` leaves raw as `\uXXXX`, so the value is unchanged and the text is inert.

The trace page puts the input in a `CodeBlock`, the steps in a mono vertical timeline (each a `details` with its kind, its verbatim subject, timing, and a copy button in its body), and a sticky judge-verdict panel beside them on desktop: every verdict with its status, kind (rule or LLM judge), score, a link to its step and its reason. Verdicts also stay under the step they concern.

## Consequences
- `X-Total-Count` costs one more count query per page of runs.
- The run page makes one more request (the suite version's cases) and, once the run ends, one more (its findings).
- Copying a step's text from the trace view is lossy for control characters by design; the trace JSON keeps them.
- `visibleText` runs on every render of untrusted text: one regex pass each, negligible next to layout.
