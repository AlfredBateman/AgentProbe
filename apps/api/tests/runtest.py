"""Helpers for run tests on either queue backend (importable: apps/api/tests is on pythonpath)."""

import asyncio
import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from agentprobe_api.queue import Deps
from agentprobe_api.runstore import TERMINAL
from agentprobe_core.runner import AttemptResult

SMOKE_YAML = (Path(__file__).parents[3] / "suites/examples/smoke.yaml").read_text("utf-8")
SUPPORT_RESPONSE = {"tool_calls": "$.tool_calls", "total_tokens": "$.usage.total_tokens"}
SMALL_YAML = """
suite: small
agent: support-v1
runs_per_case: 2
cases:
  - id: greeting
    input: "Hello there"
    expect:
      - judge: contains
        value: "How can I help?"
  - id: refund-outside-window
    input: "Can I get a refund after 45 days?"
    expect:
      - judge: contains_any
        values: ["30 days", "not eligible"]
      - judge: tool_not_called
        tool: issue_refund
      - judge: consistency
        min_agreement: 0.9
"""


async def make_project(
    client: httpx.AsyncClient,
    agent_url: str,
    *,
    yaml: str = SMALL_YAML,
    agent_name: str = "support-v1",
    auth_header: dict[str, str] | None = None,
    **agent_config: Any,
) -> dict[str, str]:
    """A project with one http agent at `agent_url` and one suite. Returns their ids."""
    project = (await client.post("/projects", json={"name": f"p-{uuid.uuid4().hex[:8]}"})).json()
    config = {
        "adapter_type": "http",
        "url": agent_url,
        "allow_private": True,
        "response": SUPPORT_RESPONSE,
        **agent_config,
    }
    body: dict[str, Any] = {"name": agent_name, "config": config}
    if auth_header:
        body["auth_header"] = auth_header
    agent = await client.post(f"/projects/{project['id']}/agents", json=body)
    assert agent.status_code == 201, agent.text
    suite = await client.post(f"/projects/{project['id']}/suites", json={"yaml": yaml})
    assert suite.status_code == 201, suite.text
    return {
        "project_id": project["id"],
        "agent_id": agent.json()["id"],
        "suite_id": suite.json()["id"],
    }


async def start_run(client: httpx.AsyncClient, suite_id: str, **body: Any) -> dict[str, Any]:
    r = await client.post(f"/suites/{suite_id}/runs", json=body)
    assert r.status_code == 202, r.text
    run: dict[str, Any] = r.json()
    return run


async def wait_for_run(
    client: httpx.AsyncClient, app: FastAPI, run_id: str, timeout_s: float = 120
) -> dict[str, Any]:
    """The run once it has ended: joins the inline queue, or polls (the Redis backend)."""
    join = getattr(app.state.queue, "join", None)
    if join is not None:
        await join()
    async with asyncio.timeout(timeout_s):
        while True:
            run: dict[str, Any] = (await client.get(f"/runs/{run_id}")).json()
            if run["status"] in TERMINAL:
                return run
            await asyncio.sleep(0.5)


def deps_of(app: FastAPI) -> Deps:
    return Deps(app.state.settings, app.state.sessionmaker, app.state.secret_box, app.state.bus)


class NullQueue:
    """Accepts runs and never executes them, so a test can drive them by hand."""

    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    async def start(self) -> None: ...

    async def enqueue(self, run_id: uuid.UUID) -> None:
        self.enqueued.append(run_id)

    async def cancel(self, run_id: uuid.UUID) -> None: ...

    async def recover(self) -> None: ...

    async def aclose(self) -> None: ...


def parse_sse(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.split("\n\n"):
        data = [line[len("data: ") :] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


_VOLATILE = {"started_at", "duration_ms", "latency_ms", "timestamp"}


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in _VOLATILE}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def normalized(results: list[AttemptResult]) -> dict[str, list[str]]:
    """Attempts per case with timings removed, as a sorted multiset: which attempt index
    drew which outcome depends on the order attempts reached the (seeded) demo agent.
    """
    by_case: defaultdict[str, list[str]] = defaultdict(list)
    for result in results:
        data = _strip(result.model_dump(mode="json", exclude={"attempt"}))
        for judgment in data["judgments"]:
            if judgment["judge"] == "latency_under":
                judgment.pop("reason")  # quotes the latency
        by_case[result.case_id].append(json.dumps(data, sort_keys=True))
    return {case: sorted(items) for case, items in by_case.items()}
