import json
from pathlib import Path

import pytest
from format_comment import code_span, escape_md, render_comment

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text("utf-8"))


def test_escape_md_neutralizes_markdown_punctuation():
    assert escape_md("a*b_c[d](e)") == r"a\*b\_c\[d\]\(e\)"


def test_escape_md_flattens_newlines():
    assert "\n" not in escape_md("line one\nline two")


def test_code_span_neutralizes_backticks_and_newlines():
    assert code_span("a`b\nc") == "`a'b c`"


def test_no_baseline_says_so_and_links_to_local_file():
    comment = render_comment(
        _load("no_baseline.json"), suite="smoke", agent="support-v1", baseline_branch="main"
    )
    assert "no baseline available" in comment
    assert "97.5%" in comment
    assert ".agentprobe/runs/20260929T120000Z-smoke-abcd1234.json" in comment
    assert "[View full run" not in comment


def test_push_regression_shows_verdict_findings_and_dashboard_link():
    comment = render_comment(
        _load("push_regression.json"), suite="smoke", agent="support-v1", baseline_branch="main"
    )
    assert "\U0001f534" in comment  # red circle
    assert "regression" in comment
    assert "`refund-outside-window`" in comment  # newly failing
    assert "`order-status`" in comment  # newly flaky
    assert "Refund policy" in comment  # cluster label, escaped
    assert "https://dashboard.example.com/runs/11111111-1111-1111-1111-111111111111" in comment
    assert "exit code 2" in comment


def test_push_regression_escapes_untrusted_cluster_text():
    comment = render_comment(
        _load("push_regression.json"), suite="smoke", agent="support-v1", baseline_branch="main"
    )
    # The finding's summary contains a literal "*outside*" that must not render as italics.
    assert "\\*outside\\*" in comment


def test_local_baseline_regression_has_no_dashboard_link_but_has_newly_failing():
    comment = render_comment(
        _load("local_baseline_regression.json"),
        suite="smoke",
        agent="support-v1",
        baseline_branch="main",
    )
    assert "`refund-outside-window`" in comment
    assert "[View full run" not in comment
    assert "Local run saved to" in comment


def test_push_no_change_has_green_icon_and_no_findings_section():
    comment = render_comment(
        _load("push_no_change.json"), suite="smoke", agent="support-v1", baseline_branch="main"
    )
    assert "⚪" in comment or "no change" in comment
    assert "Top failure clusters" not in comment


def test_untrusted_suite_and_agent_names_are_escaped_in_a_code_span():
    result = _load("no_baseline.json")
    comment = render_comment(
        result, suite="evil](javascript:x)", agent="a`gent", baseline_branch="main"
    )
    assert "evil](javascript:x)" in comment  # inert inside a code span, not a live link
    assert "`a'gent`" in comment  # backtick neutralized


def test_fallback_run_url_used_when_no_push_dashboard_url():
    result = _load("local_baseline_regression.json")
    comment = render_comment(
        result,
        suite="smoke",
        agent="support-v1",
        baseline_branch="main",
        fallback_run_url="https://example.com/artifact/42",
    )
    assert "[View full run →](https://example.com/artifact/42)" in comment


@pytest.mark.parametrize(
    "fixture", ["no_baseline.json", "push_regression.json", "push_no_change.json"]
)
def test_marker_is_always_first_line(fixture):
    comment = render_comment(_load(fixture), suite="s", agent="a", baseline_branch="main")
    assert comment.splitlines()[0] == "<!-- agentprobe-report -->"
