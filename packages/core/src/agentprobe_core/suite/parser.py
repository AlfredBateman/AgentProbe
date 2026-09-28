"""Safe YAML parsing for suite files: size limits, no anchor/alias expansion, and errors that
read like linter output (line/column for syntax, and best-effort line/column plus a field path
for schema violations, located by walking the composed YAML node tree).
"""

from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from agentprobe_core.suite.schema import Suite

MAX_FILE_BYTES = 256 * 1024


class SuiteIssue(BaseModel):
    """One problem in a suite YAML file. `line`/`col` (1-indexed) are set whenever a source
    position could be resolved: always for YAML syntax errors, best-effort for schema
    violations (located by walking the composed node tree against the error's field path).
    `path` is the dotted/bracketed pydantic field path, set only for schema violations.
    """

    model_config = ConfigDict(frozen=True)

    message: str
    path: str | None = None
    line: int | None = None
    col: int | None = None


class SuiteParseError(Exception):
    """Base for every error `parse_suite_yaml` raises. `.issues` is always non-empty."""

    def __init__(self, issues: list[SuiteIssue]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def _reject_anchors_and_aliases(text: str) -> None:
    """The simplest defence against anchor/alias expansion ("billion laughs") bombs: a suite
    YAML has no legitimate use for them, so reject the tokens outright before composing.
    """
    for token in yaml.scan(text, Loader=yaml.SafeLoader):
        if isinstance(token, yaml.AliasToken | yaml.AnchorToken):
            raise yaml.MarkedYAMLError(
                problem="anchors and aliases are not allowed in suite YAML",
                problem_mark=token.start_mark,
            )


def _format_yaml_error(exc: yaml.YAMLError) -> SuiteIssue:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or str(exc)
    if mark is None:
        return SuiteIssue(message=f"YAML syntax error: {problem}")
    return SuiteIssue(
        message=f"YAML syntax error at line {mark.line + 1}, column {mark.column + 1}: {problem}",
        line=mark.line + 1,
        col=mark.column + 1,
    )


def _locate(loc: tuple[int | str, ...], root: yaml.Node | None) -> tuple[int, int] | None:
    """Walks the composed node tree along a pydantic error's `loc` path. Returns None rather
    than raising whenever the path doesn't resolve to a node (e.g. a model-level validator
    with a partial loc) — a missing position just means the issue falls back to its `path`.
    """
    if not loc or root is None:
        return None
    node: yaml.Node | None = root
    for part in loc:
        if isinstance(node, yaml.MappingNode) and isinstance(part, str):
            node = next((value for key, value in node.value if key.value == part), None)
        elif isinstance(node, yaml.SequenceNode) and isinstance(part, int):
            node = node.value[part] if 0 <= part < len(node.value) else None
        else:
            return None
        if node is None:
            return None
    if node is None:  # loc was non-empty, so this is unreachable; satisfies mypy's narrowing
        return None
    mark = node.start_mark
    return mark.line + 1, mark.column + 1


def _compose(text: str) -> yaml.Node | None:
    try:
        return cast("yaml.Node | None", yaml.compose(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError:
        # The same text already parsed once via safe_load; composing again shouldn't fail,
        # but locating an error is never worth raising over.
        return None


def _format_validation_error(exc: ValidationError, root: yaml.Node | None) -> list[SuiteIssue]:
    issues = []
    for error in exc.errors():
        loc = error["loc"]
        path = ".".join(str(part) for part in loc) or None
        located = _locate(loc, root)
        line, col = located if located else (None, None)
        message = f"{path}: {error['msg']}" if path else error["msg"]
        issues.append(SuiteIssue(message=message, path=path, line=line, col=col))
    return issues


def parse_suite_yaml(text: str) -> Suite:
    """Parses and validates a suite YAML document. Raises `SuiteParseError` on any problem:
    oversized input, invalid YAML syntax, anchors/aliases, or a schema violation.
    """
    size = len(text.encode("utf-8"))
    if size > MAX_FILE_BYTES:
        raise SuiteParseError(
            [SuiteIssue(message=f"suite file is {size} bytes, over the {MAX_FILE_BYTES} limit")]
        )

    try:
        _reject_anchors_and_aliases(text)
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SuiteParseError([_format_yaml_error(exc)]) from exc

    if not isinstance(raw, dict):
        raise SuiteParseError([SuiteIssue(message="suite YAML must be a mapping at the top level")])

    try:
        return Suite.model_validate(raw)
    except ValidationError as exc:
        raise SuiteParseError(_format_validation_error(exc, _compose(text))) from exc


def suite_json_schema() -> dict[str, Any]:
    """JSON Schema for the suite format, for the web YAML editor."""
    return Suite.model_json_schema()
