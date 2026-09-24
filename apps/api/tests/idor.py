"""Reusable IDOR check: can one principal read or change another user's resources?

Every endpoint that takes a resource id gets a Probe in test_idor.PROBES. New endpoints
(agents, suites, runs, ...) extend PROBES and SNAPSHOT and create their resources in the
`world` fixture; this module stays as is.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

DENIED = {403, 404}


@dataclass(frozen=True)
class Probe:
    method: str
    path: str  # template filled from the owner's resource ids, e.g. "/projects/{project_id}"
    json: dict[str, Any] | None = None

    def call(self, client: httpx.AsyncClient, ids: dict[str, str]) -> Any:
        return client.request(self.method, self.path.format(**ids), json=self.json)


async def snapshot(
    owner: httpx.AsyncClient, paths: list[str], ids: dict[str, str]
) -> dict[str, Any]:
    state = {}
    for path in paths:
        r = await owner.get(path.format(**ids))
        assert r.status_code == 200, f"snapshot GET {path}: {r.status_code} {r.text}"
        state[path] = r.json()
    return state


async def assert_no_idor(
    *,
    owner: httpx.AsyncClient,
    intruder: httpx.AsyncClient,
    ids: dict[str, str],
    probes: list[Probe],
    snapshot_paths: list[str],
) -> None:
    """For every probe, the intruder is denied, the denial is indistinguishable from asking
    for an id that doesn't exist (no enumeration), and the owner's data is unchanged.
    """
    before = await snapshot(owner, snapshot_paths, ids)
    random_ids = {name: str(uuid.uuid4()) for name in ids}
    for probe in probes:
        r = await probe.call(intruder, ids)
        where = f"{probe.method} {probe.path}"
        assert r.status_code in DENIED, f"IDOR: {where} -> {r.status_code}: {r.text}"
        missing = await probe.call(intruder, random_ids)
        assert (r.status_code, r.json()["error"]["message"]) == (
            missing.status_code,
            missing.json()["error"]["message"],
        ), f"{where}: another user's resource is distinguishable from a nonexistent one"
    assert await snapshot(owner, snapshot_paths, ids) == before, "intruder changed owner's data"
