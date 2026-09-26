import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentprobe_demo_agents.main import create_app
from agentprobe_demo_agents.mcp_server import MCP_ROUTE

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "vulnerabilities.json"
REQUIRED_FIELDS = {
    "id",
    "route",
    "category",
    "description",
    "trigger",
    "suite",
    "suite_case_ids",
    "expected",
    "negative_control",
}


def test_manifest_entries_have_required_fields_and_unique_ids() -> None:
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert entries, "vulnerabilities.json must not be empty"

    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids)), "duplicate flaw ids in vulnerabilities.json"

    for entry in entries:
        assert REQUIRED_FIELDS <= entry.keys()
        assert isinstance(entry["suite_case_ids"], list)


def test_every_route_in_the_manifest_is_actually_served() -> None:
    entries = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    with TestClient(create_app()) as client:  # runs the lifespan: the MCP route needs it
        for entry in entries:
            if entry["route"] == MCP_ROUTE:
                # A real MCP handshake needs a session; the transport itself answers before
                # that (421, since TestClient's Host isn't on the allowlist), proving the
                # route is mounted rather than a plain 404.
                r = client.post(f"{MCP_ROUTE}/mcp", json={})
                assert r.status_code != 404, entry["id"]
                continue
            r = client.post(f"{entry['route']}/chat", json={"input": "hello"})
            assert r.status_code == 200, entry["id"]
