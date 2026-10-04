"""Seeds a running AgentProbe stack with the data the README's screenshots use.
Stdlib only.

    python3 scripts/seed_demo.py                                  # local dev stack
    python3 scripts/seed_demo.py --web http://localhost:3000 --agents-url http://127.0.0.1:9000

What it creates, through the web app's /api proxy, for the account it registers (or signs in to):
1. a project `support-bot`, one agent `support-bot` on the demo support bot (`/support/v1`),
   and the smoke suite (suites/examples/smoke.yaml, 9 cases x 10 attempts);
2. a run of that agent, set as the `main` baseline;
3. the same agent changed to the v2 prompt (`/support/v2`: the refund window widened from 30 to
   45 days) and run again, which the dashboard calls a regression;
4. the agent pointed at the deliberately vulnerable bot (`/vulnerable`) and run once more, so
   the Findings page has failures to cluster.

Mock LLM only (the run request's default). The API must reach `--agents-url`: on a local stack
that needs ALLOW_PRIVATE_TARGETS=1. The account must be allowed to register
(SIGNUP_ALLOWED_EMAILS or SIGNUP_OPEN=1 on the API). Prints the project and run URLs, and the ids
to delete afterwards.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SUITE = Path(__file__).resolve().parent.parent / "suites" / "examples" / "smoke.yaml"
RUN_TIMEOUT_S = 600
cookies: dict[str, str] = {}  # the session cookies are Secure, which http.cookiejar won't send


def request(web: str, method: str, path: str, body: Any = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{web}/api{path}", data=data, method=method)  # noqa: S310
    req.add_header("Origin", web)  # the API's CSRF check on cookie sessions (ADR 0009)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            status, raw, headers = resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        status, raw, headers = exc.code, exc.read(), exc.headers
    except urllib.error.URLError as exc:
        sys.exit(f"FAIL {method} {web}/api{path}: {exc.reason}")
    for cookie in headers.get_all("Set-Cookie") or []:
        name, _, rest = cookie.partition("=")
        cookies[name.strip()] = rest.split(";", 1)[0]
    payload = json.loads(raw) if raw else None
    if not 200 <= status < 300:
        sys.exit(f"FAIL {method} /api{path}: {status} {payload}")
    return payload


def agent_config(agents_url: str, route: str) -> dict[str, Any]:
    return {
        "adapter_type": "http",
        "url": f"{agents_url}{route}/chat",
        "allow_private": agents_url.startswith("http://127.") or "localhost" in agents_url,
        "response": {
            "output": "$.output",
            "tool_calls": "$.tool_calls",
            "total_tokens": "$.usage.total_tokens",
        },
    }


def run_and_wait(web: str, suite_id: str, label: str) -> dict[str, Any]:
    run = request(web, "POST", f"/suites/{suite_id}/runs", {"model": label})
    deadline = time.monotonic() + RUN_TIMEOUT_S
    while run["status"] in ("queued", "running"):
        if time.monotonic() > deadline:
            sys.exit(f"FAIL run {run['id']} still {run['status']} after {RUN_TIMEOUT_S} s")
        time.sleep(2)
        run = request(web, "GET", f"/runs/{run['id']}")
    if run["status"] != "completed":
        sys.exit(f"FAIL run {run['id']} ended {run['status']}: {run}")
    print(f"ok   {label}: pass rate {run['pass_rate']:.2f}, run {run['id']}")
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--web", default="http://localhost:3000", help="the web app's origin")
    parser.add_argument("--agents-url", default="http://127.0.0.1:9000")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demo-password-1")
    args = parser.parse_args()
    web, agents = args.web.rstrip("/"), args.agents_url.rstrip("/")

    credentials = {"email": args.email, "password": args.password}
    try:
        request(web, "POST", "/auth/register", credentials)
    except SystemExit:  # already registered: sign in instead
        request(web, "POST", "/auth/login", credentials)
    print(f"ok   signed in as {args.email}")

    project = request(web, "POST", "/projects", {"name": "support-bot"})
    pid = project["id"]
    agent = request(
        web,
        "POST",
        f"/projects/{pid}/agents",
        {"name": "support-v1", "config": agent_config(agents, "/support/v1")},
    )
    suite = request(web, "POST", f"/projects/{pid}/suites", {"yaml": SUITE.read_text("utf-8")})

    baseline = run_and_wait(web, suite["id"], "support prompt v1")
    request(web, "POST", f"/projects/{pid}/baseline", {"branch": "main", "run_id": baseline["id"]})
    print("ok   baseline set on main")

    runs = {"v1": baseline}
    for key, route, label in (
        ("v2", "/support/v2", "support prompt v2"),
        ("vulnerable", "/vulnerable", "vulnerable bot"),
    ):
        # The same agent (and suite), changed: what a prompt edit looks like to AgentProbe.
        request(
            web,
            "PUT",
            f"/agents/{agent['id']}",
            {"name": "support-v1", "config": agent_config(agents, route)},
        )
        runs[key] = run_and_wait(web, suite["id"], label)

    print(f"\nproject {pid}  {web}/projects/{pid}")
    print(f"agent   {agent['id']}")
    for key, run in runs.items():
        print(f"run {key:<10} {web}/projects/{pid}/runs/{run['id']}")
    print(f"compare v2 with the baseline: {web}/projects/{pid}/runs/{runs['v2']['id']}/compare")


if __name__ == "__main__":
    main()
