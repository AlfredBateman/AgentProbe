import json
from pathlib import Path

from agentprobe_core.suite import ATTACKS, suite_json_schema

COMMITTED = Path(__file__).resolve().parents[4] / "apps/web/src/lib/api/suite-schema.json"


def test_web_suite_schema_is_current() -> None:
    """The web YAML editor's autocomplete is generated from this file. Regenerate with
    `uv run python scripts/export_suite_schema.py`.
    """
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    expected = {
        "schema": suite_json_schema(),
        "attacks": [{"id": id_, "category": category} for id_, category in sorted(ATTACKS.items())],
    }
    assert committed == json.loads(json.dumps(expected))
