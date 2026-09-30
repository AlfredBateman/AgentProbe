"""Smoke-tests the production deploy (ADR 0035, docs/DEPLOY.md) end to end, then deletes what
it created.

Through the web app's /api proxy, as a browser would: registers a throwaway user, creates a
project, an HTTP agent on the deployed demo agents (over Fly's private network, so it also
proves the SSRF allowlist admits them) and a small suite, runs it in mock mode, and checks the
run's results, a trace, its findings and a share link, both anonymously and after revoking.
The API has no account delete, so cleanup deletes the user from the production database,
cascading to everything it owns (scripts/cleanup_e2e_account.py). It runs even when a check
fails.

    WEB_ORIGIN=https://<web> API_URL=https://<api app>.fly.dev \\
    DEMO_AGENTS_HOST=<demo app>.flycast PRODUCTION_DATABASE_URL='<Neon direct string>' \\
    uv run python scripts/smoke_prod.py

It uses one registration of the per-IP hourly limit (REGISTER_RATE_LIMIT_PER_HOUR), one run of
the new user's daily cap, and 6 attempts. Nothing calls an LLM: the run is mock and the demo
agents are rule-based.
"""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from cleanup_e2e_account import delete_user, run_async

RUN_TIMEOUT_S = 180
COLD_START_S = 90  # a stopped Fly machine starts on the first request
FAILS_ON_PURPOSE = "SMOKE-NEVER-IN-ANY-OUTPUT"
SUITE = f"""\
suite: prod-smoke
agent: smoke-support-v1
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
      - judge: tool_not_called
        tool: issue_refund
  - id: fails-on-purpose  # failing attempts with output, so the run has findings
    input: "Hello there"
    expect:
      - judge: contains
        value: "{FAILS_ON_PURPOSE}"
"""


class SmokeFailure(Exception):
    pass


class Client:
    """Keeps the session cookies by hand: they are host-only on the web origin, and the
    requests are all to that origin."""

    def __init__(self, web: str) -> None:
        self.web = web
        self.cookies: dict[str, str] = {}

    def request(
        self, method: str, url: str, body: Any = None, *, anonymous: bool = False
    ) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)  # noqa: S310  https URLs
        req.add_header("Origin", self.web)  # the API's CSRF check (ADR 0009, ADR 0035)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.cookies and not anonymous:
            req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                status, raw, headers = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            status, raw, headers = exc.code, exc.read(), exc.headers
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SmokeFailure(f"{method} {url}: {getattr(exc, 'reason', exc)}") from exc
        if not anonymous:
            for cookie in headers.get_all("Set-Cookie") or []:
                name, _, rest = cookie.partition("=")
                self.cookies[name.strip()] = rest.split(";", 1)[0]
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, raw.decode(errors="replace")[:500]

    def api(self, method: str, path: str, body: Any = None, *, expect: int | None = None) -> Any:
        status, payload = self.request(method, f"{self.web}/api{path}", body)
        if not (status == expect if expect else 200 <= status < 300):
            raise SmokeFailure(f"{method} /api{path}: {status} {payload}")
        return payload


def ok(message: str) -> None:
    print(f"ok   {message}", flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def wait_ready(client: Client, url: str) -> None:
    deadline = time.monotonic() + COLD_START_S
    while True:
        try:
            status, _ = client.request("GET", url, anonymous=True)
        except SmokeFailure:
            status = 0
        if status == 200:
            return
        if time.monotonic() > deadline:
            raise SmokeFailure(f"GET {url}: {status} after {COLD_START_S} s")
        time.sleep(3)


def smoke(client: Client, api_url: str, demo_host: str, email: str) -> None:
    web = client.web
    wait_ready(client, f"{api_url}/ready")
    ok(f"GET {api_url}/ready")
    for url in (f"{web}/api/health", f"{web}/login"):
        status, _ = client.request("GET", url, anonymous=True)
        check(status == 200, f"GET {url}: {status}")
        ok(f"GET {url}")

    client.api("POST", "/auth/register", {"email": email, "password": secrets.token_urlsafe(24)})
    check({"access_token", "refresh_token"} <= client.cookies.keys(), "no session cookies")
    check(client.api("GET", "/auth/me")["email"] == email, "/auth/me is not the new user")
    ok(f"registered {email}")

    project = client.api("POST", "/projects", {"name": "prod-smoke"})
    agent = client.api(
        "POST",
        f"/projects/{project['id']}/agents",
        {
            "name": "smoke-support-v1",
            "config": {
                "adapter_type": "http",
                "url": f"http://{demo_host}/support/v1/chat",
                "allow_private": True,  # the agent's half; the server's is the allowlist
                "response": {
                    "output": "$.output",
                    "tool_calls": "$.tool_calls",
                    "total_tokens": "$.usage.total_tokens",
                },
            },
        },
    )
    probe = client.api("POST", f"/agents/{agent['id']}/test")
    check(probe["success"], f"agent connection test: {probe['message']}")
    ok(f"agent reaches http://{demo_host} through the SSRF guard")

    suite = client.api("POST", f"/projects/{project['id']}/suites", {"yaml": SUITE})
    run = client.api("POST", f"/suites/{suite['id']}/runs", {"mock": True})
    check(run["mock_mode"], "run is not in mock mode")
    deadline = time.monotonic() + RUN_TIMEOUT_S
    while run["status"] in ("queued", "running"):
        if time.monotonic() > deadline:
            raise SmokeFailure(f"run still {run['status']} after {RUN_TIMEOUT_S} s")
        time.sleep(2)
        run = client.api("GET", f"/runs/{run['id']}")
    check(run["status"] == "completed", f"run ended {run['status']}: {run['error']}")
    check(run["attempts_done"] == run["attempts_total"] == 6, f"attempts: {run}")
    ok(f"mock run completed: 6 attempts, pass rate {run['pass_rate']:.2f}")

    results = client.api("GET", f"/runs/{run['id']}/results")
    by_case: dict[str, set[str]] = {}
    for r in results:
        by_case.setdefault(r["case"], set()).add(r["status"])
    check(len(results) == 6, f"{len(results)} results, expected 6")
    check(by_case.get("greeting") == {"passed"}, f"greeting: {by_case.get('greeting')}")
    check(by_case.get("fails-on-purpose") == {"failed"}, f"planted failure: {by_case}")
    ok(f"results: {sorted((case, sorted(s)) for case, s in by_case.items())}")

    trace = client.api("GET", f"/results/{results[0]['id']}/trace")
    check(bool(trace["steps"]) and bool(trace["judgments"]), f"empty trace: {trace}")
    check(trace["run_id"] == run["id"], "trace belongs to another run")
    ok(f"trace: {len(trace['steps'])} steps, {len(trace['judgments'])} judgments")

    findings = client.api("GET", f"/runs/{run['id']}/findings")
    failed_ids = {r["id"] for r in results if r["status"] == "failed"}
    members = {m for f in findings for m in f["member_result_ids"]}
    check(bool(findings) and members == failed_ids, f"findings {findings} vs {failed_ids}")
    ok(f"findings: {len(findings)} cluster(s) over {len(failed_ids)} failures")

    share = client.api("POST", f"/runs/{run['id']}/share", {"expires_in_days": 1})
    check(share["url"] == f"{web}/shared/{share['token']}", f"share url: {share['url']}")
    status, _ = client.request("GET", share["url"], anonymous=True)
    check(status == 200, f"GET share page: {status}")
    shared_api = f"{web}/api/shared/{share['token']}"
    status, shared = client.request("GET", shared_api, anonymous=True)
    check(status == 200 and shared["suite"] == "prod-smoke", f"shared view: {status} {shared}")
    check(len(shared["results"]) == 6, "shared view is missing results")
    ok("share link works anonymously")
    client.api("DELETE", f"/runs/{run['id']}/share", expect=204)
    status, _ = client.request("GET", shared_api, anonymous=True)
    check(status == 404, f"revoked share link answers {status}")
    ok("revoked share link is 404")


def main() -> None:
    try:
        web = os.environ["WEB_ORIGIN"].rstrip("/")
        api_url = os.environ["API_URL"].rstrip("/")
        demo_host = os.environ["DEMO_AGENTS_HOST"]
        database_url = os.environ["PRODUCTION_DATABASE_URL"]
    except KeyError as exc:
        sys.exit(f"{exc.args[0]} is not set (see this script's docstring)")
    email = f"smoke-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}@example.com"
    client = Client(web)
    failure: SmokeFailure | None = None
    try:
        smoke(client, api_url, demo_host, email)
    except SmokeFailure as exc:
        failure = exc
    finally:
        # Only an account this run registered, found by its unique throwaway address.
        deleted = run_async(delete_user(database_url, email))
        if deleted is not None:
            ok(f"deleted {email} and everything it owned")
        elif failure is None:
            failure = SmokeFailure(f"{email} is not in PRODUCTION_DATABASE_URL's database")
    if failure is not None:
        sys.exit(f"FAIL {failure}")
    print("PASS production smoke test")


if __name__ == "__main__":
    main()
