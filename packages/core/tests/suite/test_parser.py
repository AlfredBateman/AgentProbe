from pathlib import Path

import pytest

from agentprobe_core.suite.parser import (
    MAX_FILE_BYTES,
    SuiteParseError,
    parse_suite_yaml,
    suite_json_schema,
)

REPO_ROOT = Path(__file__).parents[4]
EXAMPLES_DIR = REPO_ROOT / "suites" / "examples"
EXAMPLE_SUITE = EXAMPLES_DIR / "support-agent-safety.yaml"

VALID_YAML = """
suite: demo
agent: demo-bot
runs_per_case: 3
cases:
  - id: c1
    input: "hi"
    expect:
      - judge: contains
        value: "ok"
"""


def test_valid_yaml_parses() -> None:
    suite = parse_suite_yaml(VALID_YAML)
    assert suite.suite == "demo"
    assert len(suite.cases) == 1


def test_example_suite_from_spec_parses() -> None:
    text = EXAMPLE_SUITE.read_text(encoding="utf-8")
    suite = parse_suite_yaml(text)
    assert suite.suite == "support-agent-safety"
    assert [c.id for c in suite.cases] == [
        "refund-policy-basic",
        "injection-direct",
        "tool-misuse-delete",
    ]


def test_malformed_yaml_reports_line_and_column() -> None:
    bad = "suite: demo\nagent: [unterminated\n"
    with pytest.raises(SuiteParseError) as exc_info:
        parse_suite_yaml(bad)
    message = str(exc_info.value)
    assert "line" in message and "column" in message


def test_oversized_file_rejected() -> None:
    huge = "suite: demo\nagent: a\ncases: []\n# " + ("x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(SuiteParseError, match="over the"):
        parse_suite_yaml(huge)


def test_anchor_alias_bomb_rejected() -> None:
    bomb = """
suite: demo
agent: demo-bot
cases:
  - id: c1
    input: &a ["x", "x", "x", "x", "x", "x", "x", "x", "x", "x"]
    expect:
      - judge: contains
        value: *a
"""
    with pytest.raises(SuiteParseError, match="anchors and aliases"):
        parse_suite_yaml(bomb)


def test_non_mapping_top_level_rejected() -> None:
    with pytest.raises(SuiteParseError, match="mapping"):
        parse_suite_yaml("- just\n- a\n- list\n")


def test_unknown_top_level_key_reported_with_field_path() -> None:
    bad = VALID_YAML + "extra_field: true\n"
    with pytest.raises(SuiteParseError) as exc_info:
        parse_suite_yaml(bad)
    assert any("extra_field" in (issue.path or "") for issue in exc_info.value.issues)


def test_schema_violation_locates_line_and_column() -> None:
    bad = """
suite: demo
agent: demo-bot
cases:
  - id: c1
    input: "hi"
    expect:
      - judge: contains
        value: "ok"
  - id: c1
    input: "bye"
    expect:
      - judge: contains
        value: "no"
"""
    with pytest.raises(SuiteParseError) as exc_info:
        parse_suite_yaml(bad)
    issue = next(i for i in exc_info.value.issues if "duplicate case id" in i.message)
    assert issue.path == "cases"
    assert issue.line is not None
    assert issue.col is not None


def test_model_level_violation_locates_its_containing_field() -> None:
    bad = """
suite: demo
agent: demo-bot
statistics:
  alpha: 0.05
  alpha_cases: 0.04
  alpha_suite: 0.04
cases:
  - id: c1
    input: "hi"
    expect:
      - judge: contains
        value: "ok"
"""
    with pytest.raises(SuiteParseError) as exc_info:
        parse_suite_yaml(bad)
    issue = next(i for i in exc_info.value.issues if "more than alpha" in i.message)
    assert issue.path == "statistics"
    assert issue.line is not None  # "statistics" itself still locates fine


def test_locate_returns_none_for_an_unresolvable_path() -> None:
    from agentprobe_core.suite.parser import _compose, _locate

    root = _compose(VALID_YAML)
    assert _locate((), root) is None  # empty loc: nothing to point at
    assert _locate(("no_such_key",), root) is None  # not a real key
    assert _locate(("cases", 99), root) is None  # index out of range
    assert _locate(("cases",), None) is None  # nothing was composed


def test_duplicate_case_id_reported() -> None:
    bad = """
suite: demo
agent: demo-bot
cases:
  - id: c1
    input: "a"
    expect: [{judge: contains, value: "x"}]
  - id: c1
    input: "b"
    expect: [{judge: contains, value: "y"}]
"""
    with pytest.raises(SuiteParseError, match="duplicate case id"):
        parse_suite_yaml(bad)


def test_suite_json_schema_describes_cases() -> None:
    schema = suite_json_schema()
    assert schema["title"] == "Suite"
    assert "cases" in schema["properties"]


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_every_example_suite_parses(path: Path) -> None:
    suite = parse_suite_yaml(path.read_text(encoding="utf-8"))
    assert suite.cases
