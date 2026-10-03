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
