"""One self-contained HTML export of a run (ADR 0018, `GET /runs/{id}/export?format=html`).

Every dynamic value — suite/agent names, case ids, agent output, tool-call arguments, judge
reasons — is untrusted (an attack-suite case is *designed* to make an agent say something
hostile) and goes through `html.escape()`. There is no external stylesheet, font or script,
and no `<script>` tag at all: the page is plain escaped text in inline-styled tables, so
there is nothing here for a payload to execute even if escaping were ever missed on one field.
"""

import json
from html import escape as e

from agentprobe_api.models import Run
from agentprobe_core.runner import AttemptResult, CaseResult, JudgeResult, RunSummary

_STYLE = """
body { font: 14px/1.5 -apple-system, Segoe UI, sans-serif; margin: 2rem; color: #1a1a1a; }
h1, h2 { font-weight: 600; }
table { border-collapse: collapse; width: 100%; margin: 0.5rem 0 1.5rem; }
th, td { border: 1px solid #d0d0d0; padding: 0.4rem 0.6rem; text-align: left; vertical-align: top; }
th { background: #f2f2f2; }
.pass { color: #16793f; } .fail { color: #b3261e; } .error { color: #b3261e; font-style: italic; }
.flaky { color: #9a6700; }
pre { white-space: pre-wrap; word-break: break-word; margin: 0;
  font: 12px/1.4 ui-monospace, monospace; }
.meta { color: #555; }
"""

_LABEL_CLASS = {"stable-pass": "pass", "stable-fail": "fail", "flaky": "flaky"}
_STATUS_CLASS = {"passed": "pass", "failed": "fail", "error": "error"}


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


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
        f"<td>{a.attempt}</td>"
        f"<td class='{status_class}'>{e(a.status)}</td>"
        f"<td><pre>{e(output) if output is not None else ''}</pre></td>"
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
<p class="meta">{case.summary.passes}/{case.summary.attempts} passed
  ({_pct(case.pass_rate)}, 95% Wilson {_pct(case.wilson.lower)}-{_pct(case.wilson.upper)})</p>
{f"<ul>{failures}</ul>" if failures else ""}
<table>
<tr><th>Attempt</th><th>Status</th><th>Output</th><th>Tool calls</th>
<th>Judgments</th><th>Error</th></tr>
{rows}
</table>
"""


def render_html(run: Run, summary: RunSummary) -> str:
    by_case: dict[str, list[AttemptResult]] = {}
    for attempt in summary.results:
        by_case.setdefault(attempt.case_id, []).append(attempt)

    case_rows = "".join(
        f"<tr><td>{e(c.case_id)}</td>"
        f"<td class='{_LABEL_CLASS.get(c.label, '')}'>{e(c.label)}</td>"
        f"<td>{c.summary.passes}/{c.summary.attempts}</td>"
        f"<td>{_pct(c.pass_rate)}</td></tr>"
        for c in summary.cases
    )
    sections = "".join(_case_section(c, by_case.get(c.case_id, [])) for c in summary.cases)
    title = f"AgentProbe run: {e(summary.suite)} ({str(run.id)[:8]})"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">
  Agent: {e(summary.agent)} &middot; Status: {e(run.status)}
  {f" &middot; Branch: {e(run.branch)}" if run.branch else ""}
  {f" &middot; Commit: {e(run.git_sha)}" if run.git_sha else ""}
  {f" &middot; PR #{run.pr_number}" if run.pr_number else ""}
</p>
<p class="meta">
  Pass rate: {_pct(summary.pass_rate)}
  {f" (95% CI {_pct(summary.ci.lower)}-{_pct(summary.ci.upper)})" if summary.ci else ""}
  &middot; {summary.attempts} attempts, {summary.errors} errors
  &middot; Started {run.started_at.isoformat() if run.started_at else "-"}
</p>
<table>
<tr><th>Case</th><th>Label</th><th>Passed</th><th>Rate</th></tr>
{case_rows}
</table>
{sections}
</body>
</html>
"""
