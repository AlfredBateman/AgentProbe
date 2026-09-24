"""Safe YAML parsing for suite files: size limits, no anchor/alias expansion, and errors that
read like linter output (line/column for syntax, field path for schema violations).
"""

from typing import Any

import yaml
from pydantic import ValidationError

from agentprobe_core.suite.schema import Suite

MAX_FILE_BYTES = 256 * 1024


class SuiteParseError(Exception):
    """Base for every error `parse_suite_yaml` raises. `.issues` is a list of linter-style
    one-line messages, always non-empty.
    """

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def _reject_anchors_and_aliases(text: str) -> None:
    """The simplest defence against anchor/alias expansion ("billion laughs") bombs: a suite
    YAML has no legitimate use for them, so reject the tokens outright before composing.
    """
    for token in yaml.scan(text, Loader=yaml.SafeLoader):
        if isinstance(token, yaml.AliasToken | yaml.AnchorToken):
            mark = token.start_mark
            raise yaml.YAMLError(
                f"anchors and aliases are not allowed in suite YAML "
                f"(line {mark.line + 1}, column {mark.column + 1})"
            )


def _format_yaml_error(exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or str(exc)
    if mark is None:
        return f"YAML syntax error: {problem}"
    return f"YAML syntax error at line {mark.line + 1}, column {mark.column + 1}: {problem}"


def _format_validation_error(exc: ValidationError) -> list[str]:
    issues = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "<suite>"
        issues.append(f"{loc}: {error['msg']}")
    return issues


def parse_suite_yaml(text: str) -> Suite:
    """Parses and validates a suite YAML document. Raises `SuiteParseError` on any problem:
    oversized input, invalid YAML syntax, anchors/aliases, or a schema violation.
    """
    size = len(text.encode("utf-8"))
    if size > MAX_FILE_BYTES:
        raise SuiteParseError([f"suite file is {size} bytes, over the {MAX_FILE_BYTES} limit"])

    try:
        _reject_anchors_and_aliases(text)
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SuiteParseError([_format_yaml_error(exc)]) from exc

    if not isinstance(raw, dict):
        raise SuiteParseError(["suite YAML must be a mapping at the top level"])

    try:
        return Suite.model_validate(raw)
    except ValidationError as exc:
        raise SuiteParseError(_format_validation_error(exc)) from exc


def suite_json_schema() -> dict[str, Any]:
    """JSON Schema for the suite format, for the web YAML editor."""
    return Suite.model_json_schema()
