import json
from pathlib import Path

from agentprobe_api.main import create_app
from apitest import make_settings

COMMITTED = Path(__file__).resolve().parents[3] / "apps/web/src/lib/api/openapi.json"


def test_web_client_schema_is_current() -> None:
    """The web app's typed client is generated from this file. Regenerate with
    `uv run python scripts/export_openapi.py && pnpm --filter web gen:api`.
    """
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert committed == create_app(make_settings()).openapi()
