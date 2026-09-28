"""Writes the suite JSON Schema and attack-id registry for the web YAML editor's autocomplete.
It's static (no DB state), so it's exported at build time rather than served over HTTP.

    uv run python scripts/export_suite_schema.py

packages/core/tests/suite/test_export_suite_schema.py fails when the committed file is stale.
"""

import json
from pathlib import Path

from agentprobe_core.suite import ATTACKS, suite_json_schema

OUTPUT = Path(__file__).resolve().parents[1] / "apps/web/src/lib/api/suite-schema.json"


def export() -> str:
    data = {
        "schema": suite_json_schema(),
        "attacks": [{"id": id_, "category": category} for id_, category in sorted(ATTACKS.items())],
    }
    return json.dumps(data, indent=2) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(export(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
