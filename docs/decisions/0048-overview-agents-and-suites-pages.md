# 0048: Overview, agents and suites on the brutalist system

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md), [ADR 0043](0043-ui-primitives-on-the-brutalist-system.md) and [ADR 0047](0047-app-shell-and-page-transition.md). Replaces the page-level parts of [ADR 0037](0037-project-overview-and-runs-page.md) and [ADR 0038](0038-agents-and-suites-pages.md); their data rules stand.

## Context
The project overview, Agents, Suites and a suite's page still ran on the legacy alias names inside the new shell. The brief asked for a dense telemetry board, an adapter-type list with MCP marked CLI only, a YAML editor in a mono code block with its validation errors inline, and a run button with a clear disabled and cold-start state. No API call, test id or behaviour was to change.

## Decision

### 1. The overview reads the latest run
Under the stat tiles, a Flakiness panel and a Regression panel read the **latest completed run of the selected suite**: `GET /runs/{id}/cases` for the flaky cases (label `flaky`, shown with passes over attempts) and `GET /runs/{id}/verdict` for the verdict against the baseline, in the words `verdictSummary` already produces. Both calls exist and are the ones the run page makes. Nothing new is computed in the browser, and nothing is invented: a run with no summaries yet shows "Not summarized yet", a suite with no baseline says so (the 404 is a state, not an error), and the baseline run itself says it has nothing to compare against.

The four tiles are latest pass rate, baseline, flaky cases and regressed cases. Figures count up once (the landing page's `CountUp`, over the existing `useCountUp`); each tile has a leader line (`Stat`'s `leader`). Regressed cases is the only red on the board, and only when it is above zero.

The trend charts and the latest-runs table are unchanged in behaviour; their legacy class names became tokens. The "Last run" tile became part of the suite filter row's metadata line.

### 2. Quick actions are links and one dialog
Run a suite (the same dialog), Add an agent, New suite and Create an API key. They are secondary buttons: the header's Run is the page's one primary action.

### 3. Adapter chips; MCP says "CLI only"
A chip is a bordered mono word (`HTTP`, `MCP`), not a status: the `Badge` marks mean pass, fail and the like, and an adapter type is none of those. Above the agents table, one chip per type in the project with its count; in each row, the agent's type under its name. `mcp` carries a "CLI only" micro note beside it, because `runs.py` refuses to run any non-HTTP agent on the server (`"{adapter_type} agents can't run on the server yet"`); a saved MCP agent can be tested here and its suites run with the CLI. The note's source is one set (`CLI_ONLY`) next to the chip. The adapter `<select>` in the dialog stays a native select (the e2e and the keyboard story both depend on it) and shows the chip and the sentence when MCP is chosen.

Delete is a danger button (red means destructive) in the row and in its confirmation.

### 4. The suite editor is a textarea inside `CodeBlock`
`CodeBlock` gained `body`, `footer` and `invalid`: the same frame, caption and copy button, with the read-only `<pre>` swapped for the editor and the validation list sitting under it, divided by a line. `YamlEditor` supplies a line-number gutter beside a plain `<textarea>` (`wrap="off"`, so a line is a line and the numbers stay aligned; the gutter scrolls with the text). A line a problem points at gets a red number and the fail mark, and the problem is listed in the frame as a button that selects its line. Red marks never stand alone: each is also in the list, in words.

What this is not: syntax highlighting or a code-editor dependency. A textarea keeps the browser's undo, selection, IME and mobile keyboard, adds no dependency, and cannot render what is typed into it as HTML. A highlighter would need a tokenizer for untrusted text for no behaviour the tests ask for.

### 5. The run button states its reason
`RunButton` reads `wakeStatus` (ADR 0047 §4). While the API is `waking` it is disabled, reads "Waking…" and says why in words ("about 30 to 40 seconds; Run unlocks when it answers"); while `down` it is disabled and says to reload. `checking` stays enabled: the request finds out, and the API client holds a mutation until the API has answered, so a click is never lost. A page can add its own reason (`blocked`). In a table row the reason stays in a screen-reader-only live region and the label alone changes.

On the suite page Run is secondary: Save is the one primary action in the editor view.

### 6. Verbatim titles
A suite's name is data. `PageHeader` takes `verbatim`, which keeps the user's case and lets a long name break anywhere, instead of the display tier's uppercase.

## Consequences
- The overview makes two more requests once a latest run exists. Both are cheap reads of rows the run already wrote.
- `RunButton` is the place to change if a page ever needs the cold-start wording to differ.
- The `CLI_ONLY` set must follow `runs.py`: when the server learns to run MCP agents, remove the entry and the sentence in the dialog.
- `RunsTable`, `trend-charts`, `RunSuiteDialog` and `suite-panels` are shared with pages not rebuilt yet (Runs); only their class names changed, to the tokens the aliases point at.
