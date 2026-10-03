"""Formats the AgentProbe GitHub Action's PR comment from `agentprobe run --json`'s output
(packages/cli/src/agentprobe/main.py). Pure formatting logic (`render_comment`) is separated
from the CLI wrapper (`main`) so it can be unit-tested against fixtures with no subprocess.

Every interpolated string here (suite/agent/branch names, case ids, cluster labels and
summaries) can come from suite YAML an attacker edited, or from an LLM cluster summary of the
agent's own output, so all of it counts as untrusted per CLAUDE.md and must never reopen
Markdown/HTML syntax in the rendered GitHub comment (ADR 0019's escaping requirement).
"""

import argparse
import json
import re
import sys
from typing import Any

MARKER_PREFIX = "<!-- agentprobe-report"
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+.!|<>~-])")
_VERDICT_ICON = {
    "regression": "\U0001f534",  # red circle
    "improvement": "\U0001f7e2",  # green circle
    "no_change": "⚪",  # white circle
    "no_baseline": "⚪",
}


def marker_for(suite: str, agent: str) -> str:
    """The hidden first line that identifies this suite/agent pair's comment. One per pair
    (ADR 0032), so parallel matrix jobs each keep their own comment instead of overwriting one.
    Only characters that are safe inside an HTML comment survive.
    """
    safe = re.compile(r"[^A-Za-z0-9._/]")
    return f"{MARKER_PREFIX}: {safe.sub('_', suite)}__{safe.sub('_', agent)} -->"


def escape_md(text: str) -> str:
    """For prose (cluster summaries, suggested fixes): escapes CommonMark punctuation and
    flattens newlines, so untrusted text can't break out of the comment's structure.
    """
    return _MD_SPECIAL.sub(r"\\\1", text.replace("\n", " "))


def code_span(text: str) -> str:
    """For identifiers (suite/agent/branch names, case ids, file paths). A code span doesn't
    interpret Markdown inside it, so the only character that matters is the backtick itself.
    """
    return f"`{text.replace(chr(96), chr(39)).replace(chr(10), ' ')}`"


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _case_list(ids: list[str]) -> str:
    return ", ".join(code_span(c) for c in ids) if ids else "none"


def render_comment(
    result: dict[str, Any],
    *,
    suite: str,
    agent: str,
    baseline_branch: str,
    fallback_run_url: str | None = None,
) -> str:
    run = result["run"]
    push = result.get("push")
    # A server push's comparison (ADR 0018/0020) takes precedence; otherwise fall back to a
    # local `--baseline` comparison (the dogfood workflow's workflow-artifact baseline, ADR 0032).
    comparison = push["comparison"] if push else result.get("regression")
    verdict = push["verdict"] if push else (comparison["verdict"] if comparison else "no_baseline")
    top_findings = (push or {}).get("top_findings") or []
    dashboard_url = (push or {}).get("dashboard_url") or fallback_run_url

    title = code_span(suite) if not agent else f"{code_span(suite)} / {code_span(agent)}"
    lines = [marker_for(suite, agent), f"## AgentProbe report: {title}", ""]

    ci = run.get("ci")
    dash = chr(0x2013)  # en dash; chr() avoids an ambiguous unicode literal in source (RUF001)
    ci_text = f" (95% CI {_pct(ci['lower'])}{dash}{_pct(ci['upper'])})" if ci else ""
    lines.append(f"**Pass rate:** {_pct(run.get('pass_rate'))}{ci_text}")

    icon = _VERDICT_ICON.get(verdict, "⚪")
    verdict_text = verdict.replace("_", " ")
    # A server compares against a branch's baseline; without one, the baseline is a run file.
    target = code_span(baseline_branch) if push else "the baseline run"
    if comparison is None:
        lines.append(
            f"**Verdict vs {target}:** {icon} no baseline available "
            "(ran without a server or local baseline; see the job log)"
        )
    else:
        lines.append(f"**Verdict vs {target}:** {icon} {verdict_text}")
        lines.append(f"\n**Newly failing:** {_case_list(comparison.get('newly_failing') or [])}")
        lines.append(f"\n**Newly flaky:** {_case_list(comparison.get('newly_flaky') or [])}")

    if top_findings:
        lines.append("\n**Top failure clusters:**")
        for i, finding in enumerate(top_findings, 1):
            n = finding["member_count"]
            lines.append(
                f"{i}. **{escape_md(finding['label'])}** ({n} case{'s' if n != 1 else ''}) — "
                f"{escape_md(finding['summary'])}"
            )
            if finding.get("suggested_fix"):
                lines.append(f"   _Suggested fix: {escape_md(finding['suggested_fix'])}_")

    if dashboard_url:
        lines.append(f"\n[View full run →]({dashboard_url})")
    elif result.get("file"):
        run_file = code_span(result["file"])
        lines.append(f"\n_Local run saved to {run_file}; no dashboard configured._")

    lines.append(f"\n<sub>exit code {result.get('exit_code', '?')}</sub>")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, help="agentprobe run --json output file")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--baseline-branch", required=True)
    parser.add_argument("--fallback-run-url", default=None)
    parser.add_argument("--comment-out", required=True, help="where to write the comment body")
    parser.add_argument("--github-output", required=True, help="$GITHUB_OUTPUT file to append to")
    args = parser.parse_args(argv)

    with open(args.result, encoding="utf-8") as f:
        result = json.load(f)

    comment = render_comment(
        result,
        suite=args.suite,
        agent=args.agent,
        baseline_branch=args.baseline_branch,
        fallback_run_url=args.fallback_run_url,
    )
    with open(args.comment_out, "w", encoding="utf-8") as f:
        f.write(comment)

    push = result.get("push")
    comparison = push["comparison"] if push else result.get("regression")
    verdict = push["verdict"] if push else (comparison["verdict"] if comparison else "no_baseline")
    run_url = (push or {}).get("dashboard_url") or ""
    pass_rate = result["run"].get("pass_rate")

    with open(args.github_output, "a", encoding="utf-8") as f:
        f.write(f"pass-rate={'' if pass_rate is None else pass_rate}\n")
        f.write(f"verdict={verdict}\n")
        f.write(f"run-url={run_url}\n")
        f.write(f"exit-code={result.get('exit_code', '')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
