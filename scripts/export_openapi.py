"""Writes the API's OpenAPI schema for the web client's generated types.

    uv run python scripts/export_openapi.py && pnpm --filter web gen:api

apps/api/tests/test_openapi_schema.py fails when the committed file is stale.
"""

import json
from pathlib import Path

from agentprobe_api.main import create_app
from agentprobe_api.settings import Settings

OUTPUT = Path(__file__).resolve().parents[1] / "apps/web/src/lib/api/openapi.json"


def schema() -> str:
    return json.dumps(create_app(Settings()).openapi(), indent=2) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(schema(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}")
