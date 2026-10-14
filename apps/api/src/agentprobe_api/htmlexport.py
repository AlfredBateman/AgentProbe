"""One self-contained HTML export of a run (ADR 0018, `GET /runs/{id}/export?format=html`).

Every dynamic value — suite/agent names, case ids, agent output, tool-call arguments, judge
reasons — is untrusted (an attack-suite case is *designed* to make an agent say something
hostile) and goes through `html.escape()`. There is no external stylesheet, font, image or
script, and no `<script>` tag at all: the page is plain escaped text in inline-styled tables, so
there is nothing here for a payload to execute even if escaping were ever missed on one field.

It matches the dashboard's telemetry look (ADR 0050): a near-black sheet, 1px lines, mono labels,
lime for the run's own marks and red only for failure. The charts are spans positioned in
percentages (no SVG, no image), each with its numbers written beside it as text. Fonts are the
reader's own: the named families if installed, system fallbacks otherwise.
"""

import json
from html import escape as e

from agentprobe_api.models import Run
from agentprobe_core.runner import AttemptResult, CaseResult, JudgeResult, RunSummary

_STYLE = """
:root { --canvas:#0a0a0a; --s1:#121212; --line:#2e2e2e; --strong:#707070; --ink:#eaeaea;
  --muted:#9a9a9a; --lime:#caff00; --red:#ff2a2a;
  --sans:Archivo,"Arial Narrow","Helvetica Neue",Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace; }
* { box-sizing:border-box; border-radius:0; }
html { background:var(--canvas); }
body { max-width:1200px; margin:0 auto; padding:0 24px 48px; background:var(--canvas);
  color:var(--ink); font:15px/1.5 var(--sans); }
.strip { margin:0 -24px; border-bottom:1px solid var(--strong); background:var(--s1);
  padding:8px 24px; font:500 10px/1.2 var(--mono); letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); }
.strip b { color:var(--lime); font-weight:500; }
h1 { margin:24px 0 8px; font:800 36px/.95 var(--sans); letter-spacing:-.03em;
  overflow-wrap:anywhere; }
h2 { margin:32px 0 4px; padding-top:16px; border-top:1px solid var(--strong);
  font:700 15px/1.3 var(--mono); overflow-wrap:anywhere; }
p { margin:4px 0; }
.k { font:500 10px/1.2 var(--mono); letter-spacing:.1em; text-transform:uppercase;
  color:var(--muted); }
.meta { font:400 12px/1.5 var(--mono); color:var(--muted); letter-spacing:.04em; }
.meta b { color:var(--ink); font-weight:400; }
.code { font-family:var(--mono); }
table { width:100%; border-collapse:collapse; margin:8px 0 24px; border:1px solid var(--line); }
th, td { border-top:1px solid var(--line); padding:8px 12px; text-align:left; vertical-align:top; }
th { background:var(--s1); border-top:0; border-bottom:1px solid var(--strong);
  font:500 10px/1.2 var(--mono); letter-spacing:.1em; text-transform:uppercase; color:var(--muted);
  white-space:nowrap; }
td.n, th.n { text-align:right; white-space:nowrap; font-family:var(--mono); }
.tiles { border:1px solid var(--line); table-layout:fixed; }
.tiles td { border-top:0; border-left:1px solid var(--line); padding:16px; }
.tiles td:first-child { border-left:0; }
.tile span { display:block; }
.tile .v { font:800 32px/1 var(--sans); letter-spacing:-.03em; margin:12px 0;
  font-variant-numeric:tabular-nums; }
.tile .v.bad { color:var(--red); }
.fig { margin:24px 0 8px; font:500 11px/1.3 var(--mono); letter-spacing:.08em;
  text-transform:uppercase; }
.fig span { color:var(--muted); }
.ruler { position:relative; display:block; height:24px; width:100%; min-width:120px;
  border-left:1px solid var(--strong); border-right:1px solid var(--strong); }
.ruler::before { content:""; position:absolute; left:0; right:0; top:50%; height:1px;
  background:var(--strong); }
.wh { position:absolute; top:50%; height:1px; background:var(--lime); }
.wh::before, .wh::after { content:""; position:absolute; top:-6px; height:13px; width:1px;
  background:var(--lime); }
.wh::before { left:0; }
.wh::after { right:0; }
.pt { position:absolute; top:50%; width:10px; height:10px; margin:-5px 0 0 -5px;
  background:var(--lime); }
.axis { display:flex; justify-content:space-between; margin-top:4px;
  font:500 10px/1.2 var(--mono); letter-spacing:.1em; color:var(--muted); }
.rw { width:180px; }
.m { display:inline-block; width:10px; height:10px; margin:0 2px 2px 0; vertical-align:middle;
  font:700 9px/10px var(--mono); text-align:center; color:var(--canvas); }
.m.p { background:var(--lime); }
.m.f { background:var(--red); }
.m.e { border:1px solid var(--muted); color:var(--muted); line-height:8px; }
.bars td { border-top:0; padding:6px 12px; }
.bars { border:0; }
.bars .lab { width:140px; font:500 11px/1.3 var(--mono); letter-spacing:.08em;
  text-transform:uppercase; }
.track { display:block; height:12px; border-left:1px solid var(--strong); }
.bar { display:block; height:12px; min-width:2px; }
.bar.p { background:var(--lime); }
.bar.f { background:var(--red); }
/* Flaky: a dashed ink outline, the flaky chip's edge. The app hatches it with an SVG mask,
   which this file's CSP (no images) would block; a colour ramp would break DESIGN.md. */
.bar.k { border:1px dashed var(--ink); }
.pass { color:var(--ink); }
.fail { color:var(--red); }
.error { color:var(--muted); font-style:italic; }
.flaky { color:var(--ink); border-bottom:1px dashed var(--ink); }
pre { white-space:pre-wrap; word-break:break-word; margin:0; font:12px/1.4 var(--mono); }
ul { margin:4px 0; padding-left:20px; }
li { margin:2px 0; }
@media (max-width:700px) {
  body { padding:0 16px 32px; }
  .strip { margin:0 -16px; padding:8px 16px; }
  /* A wide table scrolls inside its own box; its cells keep a readable width. */
  table { display:block; overflow-x:auto; }
  th, td { min-width:88px; }
  td.o { min-width:240px; }
  .tiles, .bars { display:table; }
  .tiles td, .bars td { min-width:0; }
  .tiles td { padding:12px 8px; }
  .tile .v { font-size:22px; margin:8px 0; }
}
"""

_LABEL_CLASS = {"stable-pass": "pass", "stable-fail": "fail", "flaky": "flaky"}
_STATUS_CLASS = {"passed": "pass", "failed": "fail", "error": "error"}
_LABEL_TEXT = {"stable-pass": "Stable pass", "stable-fail": "Stable fail", "flaky": "Flaky"}


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _at(value: float) -> str:
    """A rate as a left offset on a 0..100% ruler. The values are computed floats, not input."""
    return f"{max(0.0, min(1.0, value)) * 100:.2f}%"


def _ruler(value: float | None, lower: float | None, upper: float | None) -> str:
    """A rate on a fixed 0 to 100% ruler: a square at the value, a whisker over its interval."""
    inner = ""
    if lower is not None and upper is not None:
        width = max(0.0, min(1.0, upper) - max(0.0, lower)) * 100
        inner += f'<span class="wh" style="left:{_at(lower)};width:{width:.2f}%"></span>'
    if value is not None:
        inner += f'<span class="pt" style="left:{_at(value)}"></span>'
    return f'<span class="ruler">{inner}</span>'


def _axis() -> str:
    return '<span class="axis"><span>0%</span><span>50%</span><span>100%</span></span>'


def _strip(attempts: list[AttemptResult]) -> str:
    """One mark per attempt, in order. The shapes carry the meaning, not only the colour."""
    marks = {"passed": ("p", ""), "failed": ("f", "&times;"), "error": ("e", "!")}
    out = []
    for a in sorted(attempts, key=lambda a: a.attempt):
        cls, glyph = marks.get(a.status, ("e", "!"))
        out.append(f'<span class="m {cls}">{glyph}</span>')
    return "".join(out)


def _judgments(judgments: list[JudgeResult]) -> str:
    if not judgments:
        return ""
    rows = "".join(
        f"<li><b>{e(j.judge)}</b> [{e(j.status)}]: {e(j.reason)}</li>" for j in judgments
    )
    return f"<ul>{rows}</ul>"


def _attempt_row(a: AttemptResult) -> str:
    status_class = _STATUS_CLASS.get(a.status, "")
    output = a.response.output if a.response else None
    tool_calls = (
        json.dumps(
            [{"tool": t.tool, "arguments": t.arguments} for t in a.response.tool_calls],
            indent=2,
        )
        if a.response and a.response.tool_calls
        else None
    )
    error = a.error.message if a.error else None
    return (
        "<tr>"
        f"<td class='n'>{a.attempt}</td>"
        f"<td class='{status_class}'>{e(a.status)}</td>"
        f"<td class='o'><pre>{e(output) if output is not None else ''}</pre></td>"
        f"<td><pre>{e(tool_calls) if tool_calls else ''}</pre></td>"
        f"<td>{_judgments(a.judgments)}</td>"
        f"<td class='error'>{e(error) if error else ''}</td>"
        "</tr>"
    )


def _case_section(case: CaseResult, attempts: list[AttemptResult]) -> str:
    label_class = _LABEL_CLASS.get(case.label, "")
    failures = "".join(f"<li>{e(f)}</li>" for f in case.failures)
    rows = "".join(_attempt_row(a) for a in sorted(attempts, key=lambda a: a.attempt))
    return f"""
<h2>{e(case.case_id)} <span class="{label_class}">[{e(case.label)}]</span></h2>
<p class="meta">{_strip(attempts)} <b>{case.summary.passes}/{case.summary.attempts}</b> passed
  ({_pct(case.pass_rate)}, 95% Wilson {_pct(case.wilson.lower)}-{_pct(case.wilson.upper)})</p>
{f"<ul>{failures}</ul>" if failures else ""}
<table>
<tr><th>Attempt</th><th>Status</th><th>Output</th><th>Tool calls</th>
<th>Judgments</th><th>Error</th></tr>
{rows}
</table>
"""


def _tile(label: str, value: str, note: str = "", bad: bool = False) -> str:
    return (
        f'<td class="tile"><span class="k">{e(label)}</span>'
        f'<span class="v{" bad" if bad else ""}">{e(value)}</span>'
        f'<span class="k">{e(note)}</span></td>'
    )


def _stability_bars(summary: RunSummary) -> str:
    total = len(summary.cases)
    rows = []
    for label, cls in (("stable-pass", "p"), ("flaky", "k"), ("stable-fail", "f")):
        n = sum(1 for c in summary.cases if c.label == label)
        share = n / total if total else 0.0
        rows.append(
            f'<tr><td class="lab">{e(_LABEL_TEXT[label])}</td>'
            f'<td><span class="track"><span class="bar {cls}" '
            f'style="width:{share * 100:.2f}%"></span></span></td>'
            f'<td class="n">{n} ({_pct(share if total else None)})</td></tr>'
        )
    return f'<table class="bars" aria-label="Cases by stability">{"".join(rows)}</table>'


def render_html(run: Run, summary: RunSummary) -> str:
    by_case: dict[str, list[AttemptResult]] = {}
    for attempt in summary.results:
        by_case.setdefault(attempt.case_id, []).append(attempt)

    case_rows = "".join(
        f"<tr><td class='code'>{e(c.case_id)}</td>"
        f"<td class='{_LABEL_CLASS.get(c.label, '')}'>{e(c.label)}</td>"
        f"<td>{_strip(by_case.get(c.case_id, []))}</td>"
        f"<td class='n'>{c.summary.passes}/{c.summary.attempts}</td>"
        f"<td class='n'>{_pct(c.pass_rate)}</td>"
        f"<td class='n'>{_pct(c.wilson.lower)}-{_pct(c.wilson.upper)}</td>"
        f"<td class='rw'>{_ruler(c.pass_rate, c.wilson.lower, c.wilson.upper)}</td></tr>"
        for c in summary.cases
    )
    sections = "".join(_case_section(c, by_case.get(c.case_id, [])) for c in summary.cases)
    title = f"AgentProbe run: {e(summary.suite)} ({str(run.id)[:8]})"

    ci = summary.ci
    confidence = f"{summary.confidence * 100:.0f}%"
    interval = f"{confidence} CI {_pct(ci.lower)}-{_pct(ci.upper)}" if ci else "No interval"
    failed = sum(1 for a in summary.results if a.status == "failed")
    stable = sum(1 for c in summary.cases if c.label == "stable-pass")
    flaky = sum(1 for c in summary.cases if c.label == "flaky")
    broken = sum(1 for c in summary.cases if c.label == "stable-fail")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<p class="strip"><b>[ Run report ]</b> /// {e(run.status)} /// A self-contained export:
  no scripts, no external requests</p>
<h1>{e(summary.suite)}</h1>
<p class="meta">
  Run <b>{str(run.id)[:8]}</b> &middot; Agent: <b>{e(summary.agent)}</b> &middot; Status: <b>{
        e(run.status)
    }</b>
  {f" &middot; Branch: <b>{e(run.branch)}</b>" if run.branch else ""}
  {f" &middot; Commit: <b>{e(run.git_sha)}</b>" if run.git_sha else ""}
  {f" &middot; PR #{run.pr_number}" if run.pr_number else ""}
</p>
<p class="meta">
  Started {run.started_at.isoformat() if run.started_at else "-"}
  &middot; {summary.runs_per_case} attempts per case
</p>
<table class="tiles" aria-label="Run totals"><tr>
{_tile("Pass rate", _pct(summary.pass_rate), interval)}
{
        _tile(
            "Cases",
            str(len(summary.cases)),
            f"{stable} stable / {flaky} flaky / {broken} failing",
            bad=broken > 0,
        )
    }
{_tile("Attempts", str(summary.attempts), f"{summary.attempts - failed - summary.errors} passed")}
{_tile("Failed", str(failed), f"{summary.errors} errors", bad=failed > 0)}
</tr></table>
<p class="fig">Fig. 01 <span>/// Pass rate, {e(confidence)} interval, scale 0 to 100%</span></p>
{_ruler(summary.pass_rate, ci.lower if ci else None, ci.upper if ci else None)}
{_axis()}
<p class="meta">Pass rate <b>{_pct(summary.pass_rate)}</b>, {e(interval)}.</p>
<p class="fig">Fig. 02 <span>/// Cases by stability</span></p>
{_stability_bars(summary)}
<p class="fig">Fig. 03 <span>/// Attempts per case, and each case's 95% Wilson interval</span></p>
<table>
<tr><th>Case</th><th>Label</th><th>Attempts</th><th class="n">Passed</th><th class="n">Rate</th>
<th class="n">95% Wilson</th><th>0 to 100%</th></tr>
{case_rows}
</table>
{sections}
</body>
</html>
"""
