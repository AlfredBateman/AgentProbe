"""Talking to the AgentProbe server: `agentprobe run --push` uploads a finished local run to
`POST /ci/report` (ADRs 0019, 0020), which stores it and compares it with the branch's
baseline; `fetch` downloads a run by id from `GET /runs/{id}/export`, for `compare`/
`--baseline` given a server run id instead of a local file.

The server's URL and project API key come from the environment (AGENTPROBE_API_URL,
AGENTPROBE_API_KEY), never from agentprobe.yaml, so the key stays out of the repo.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from agentprobe_core.runner import RunSummary

URL_ENV = "AGENTPROBE_API_URL"
KEY_ENV = "AGENTPROBE_API_KEY"
TIMEOUT_S = 60.0


class PushError(Exception):
    """The upload failed. `infra`: the server couldn't be reached or failed (exit 4);
    otherwise it refused the request (exit 3: fix the config, key or suite).
    """

    def __init__(self, message: str, *, infra: bool) -> None:
        super().__init__(message)
        self.infra = infra


@dataclass(frozen=True)
class Target:
    url: str
    api_key: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Target":
        url, key = env.get(URL_ENV, ""), env.get(KEY_ENV, "")
        if not url.startswith(("https://", "http://")) or not key:
            raise PushError(f"--push needs {URL_ENV} (http(s)://...) and {KEY_ENV}", infra=False)
        return cls(url.rstrip("/"), key)


def payload(
    summary: RunSummary,
    *,
    registered: bool,
    mock: bool,
    branch: str,
    baseline_branch: str | None = None,
    git_sha: str | None = None,
    pr_number: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """The /ci/report body. An agent the server can't have registered (the python adapter)
    goes as `agent_name`, a registered one as `agent` (ADR 0020).
    """
    body: dict[str, Any] = {
        "suite": summary.suite,
        "agent" if registered else "agent_name": summary.agent,
        "results": [result.model_dump(mode="json") for result in summary.results],
        "runs_per_case": summary.runs_per_case,
        "mock": mock,
        "branch": branch,
        "baseline_branch": baseline_branch,
        "git_sha": git_sha,
        "pr_number": pr_number,
        "model": model,
    }
    return {name: value for name, value in body.items() if value is not None}


def _error_message(response: httpx.Response) -> str:
    try:
        message: str = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.reason_phrase
    return message


async def push(
    target: Target, body: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """POSTs the run. Returns the server's JSON (`run_id`, `verdict`, `comparison`, ...)."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT_S) as client:
            response = await client.post(
                f"{target.url}/ci/report",
                json=body,
                headers={"Authorization": f"Bearer {target.api_key}"},
            )
    except httpx.HTTPError as exc:
        raise PushError(f"can't reach {target.url}: {type(exc).__name__}", infra=True) from None
    if response.status_code != 201:
        raise PushError(
            f"the server refused the run (HTTP {response.status_code}): {_error_message(response)}",
            infra=response.status_code >= 500,
        )
    result: dict[str, Any] = response.json()
    return result


async def fetch(
    target: Target, run_id: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> RunSummary:
    """GETs a run's export from the server (`compare`/`--baseline` with a server run id)."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT_S) as client:
            response = await client.get(
                f"{target.url}/runs/{run_id}/export",
                params={"format": "json"},
                headers={"Authorization": f"Bearer {target.api_key}"},
            )
    except httpx.HTTPError as exc:
        raise PushError(f"can't reach {target.url}: {type(exc).__name__}", infra=True) from None
    if response.status_code != 200:
        raise PushError(
            f"can't fetch run {run_id} (HTTP {response.status_code}): {_error_message(response)}",
            infra=response.status_code >= 500,
        )
    return RunSummary.model_validate(response.json()["summary"])
