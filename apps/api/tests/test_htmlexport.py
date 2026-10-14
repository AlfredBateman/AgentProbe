"""XSS regression for the HTML export, offline: a hostile value in every field the page shows
(suite and agent names, branch, commit, agent output, tool calls, judge names and reasons,
error messages) comes out as escaped text. test_export.py covers the endpoint end to end.
"""

import re
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser

from agentprobe_api.htmlexport import render_html
from agentprobe_api.models import Run
from agentprobe_core.adapters.types import AgentResponse, MessageStep, ToolCallStep
from agentprobe_core.runner import AttemptError, AttemptResult, JudgeResult, finalize_run
from agentprobe_core.suite import parse_suite_yaml

XSS = """<script>alert(1)</script><img src=x onerror=alert(2)>"'><svg onload=alert(3)>"""
SUITE = parse_suite_yaml("""
suite: hostile
agent: bot
runs_per_case: 2
cases:
  - id: hostile-case
    input: hi
    expect:
      - judge: contains
        value: ok
""")


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: set[str] = set()
        self.attrs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self.attrs |= {name for name, _ in attrs}


def attempt(n: int, **over: object) -> AttemptResult:
    return AttemptResult.model_validate(
        {
            "case_id": "hostile-case",
            "attempt": n,
            "input": XSS,
            "status": "failed",
            "response": AgentResponse(
                output=XSS,
                steps=[
                    MessageStep(role="assistant", content=XSS),
                    ToolCallStep(tool=XSS, arguments={XSS: XSS}),
                ],
                latency_ms=1.0,
                tool_calls_reported=True,
            ),
            "judgments": [JudgeResult(judge=XSS, status="fail", score=0.0, reason=XSS)],
            "score": 0.0,
            "latency_ms": 1.0,
            "started_at": datetime.now(UTC),
            "duration_ms": 1.0,
            **over,
        }
    )


async def test_xss_html_export_escapes_every_untrusted_field() -> None:
    error = AttemptError(kind="agent", message=XSS)
    results = [attempt(0), attempt(1, status="error", error=error)]
    summary = (await finalize_run(results, suite=SUITE, agent="bot")).model_copy(
        update={"suite": XSS, "agent": XSS}
    )
    run = Run(id=uuid.uuid4(), status="completed", branch=XSS, git_sha=XSS, pr_number=7)

    page = render_html(run, summary)

    parser = Tags()
    parser.feed(page)
    # Only the page's own markup: no script, image, svg, link or form, and no event handlers.
    assert parser.tags <= {
        "html", "head", "meta", "title", "style", "body", "h1", "h2", "p", "span",
        "table", "tr", "th", "td", "pre", "ul", "li", "b",
    }  # fmt: skip
    assert not {a for a in parser.attrs if a.startswith("on")}
    assert "<script" not in page and "<img" not in page and "<svg" not in page
    escaped = re.escape("&lt;script&gt;alert(1)&lt;/script&gt;")
    # suite (title and h1), agent, branch, commit, and per attempt: output, judge, reason; the
    # error's message once; tool calls as escaped JSON.
    assert len(re.findall(escaped, page)) >= 2 + 3 + 2 * 3 + 1


def _plain_attempt(case: str, n: int, status: str) -> AttemptResult:
    """A non-hostile attempt, so the chart assertions read plainly."""
    return AttemptResult.model_validate(
        {
            "case_id": case,
            "attempt": n,
            "input": "hi",
            "status": status,
            "response": AgentResponse(output="ok", steps=[], latency_ms=1.0),
            "judgments": [JudgeResult(judge="contains", status="pass", score=1.0, reason="found")],
            "score": 1.0 if status == "passed" else 0.0,
            "latency_ms": 1.0,
            "started_at": datetime.now(UTC),
            "duration_ms": 1.0,
        }
    )


async def test_export_is_self_contained_and_charts_state_real_values() -> None:
    results = [_plain_attempt("hostile-case", n, "passed" if n < 3 else "failed") for n in range(4)]
    summary = await finalize_run(results, suite=SUITE, agent="bot")
    run = Run(id=uuid.uuid4(), status="completed", branch="main", git_sha=None, pr_number=None)

    page = render_html(run, summary)

    # No request of any kind: nothing to fetch, import, link or submit. The page's CSP is
    # `default-src 'none'`, so even a data: URI would be blocked.
    assert not re.search(r"https?://|url\(|@import|<link|<img|<svg|<form|src=|href=", page)
    assert "<script" not in page

    # Fig. 01: the whisker sits on the run's own pass rate (3 of 4 = 75%) and its interval.
    assert summary.ci is not None and summary.pass_rate == 0.75
    assert 'class="pt" style="left:75.00%"' in page
    lower, upper = summary.ci.lower, summary.ci.upper
    assert f'class="wh" style="left:{lower * 100:.2f}%;width:{(upper - lower) * 100:.2f}%"' in page

    # One mark per attempt, with its own shape: three passes, one failure (a cross).
    case_strip = re.findall(r'<span class="m (\w)">', page)
    assert case_strip.count("p") == 6 and case_strip.count("f") == 2  # the table and the section

    # Fig. 02: the single case is flaky (3 of 4), so only the flaky bar is full width.
    assert re.search(r'<span class="bar k" style="width:100.00%">', page)
    assert re.search(r'<span class="bar p" style="width:0.00%">', page)
    # The numbers are text beside the charts, not only shapes.
    assert "75.0%" in page and "3/4" in page and "95% CI" in page
