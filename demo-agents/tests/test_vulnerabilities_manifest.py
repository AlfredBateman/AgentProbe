import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentprobe_demo_agents.main import create_app

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "vulnerabilities.json"
REQUIRED_FIELDS = {"id", "route", "category", "description", "trigger", "suite_case_ids"}


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
    client = TestClient(create_app())
    for entry in entries:
        r = client.post(f"{entry['route']}/chat", json={"input": "hello"})
        assert r.status_code == 200, entry["id"]
