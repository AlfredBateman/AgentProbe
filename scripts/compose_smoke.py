"""Smoke-tests the `docker compose up` stack from the host, as the README's Docker quick start
does (CI's docker job runs exactly that).

Checks the API's and the web app's health, then registers a user, creates a project, an HTTP
agent on the demo agents and the smoke suite, runs it on the Redis worker, and waits for a pass
rate. Everything after the health checks goes through the web app's /api rewrite, so it also
proves the web container reaches the API.

Stdlib only, so any Python 3.9+ runs it: python3 scripts/compose_smoke.py
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "http://localhost:8000"
WEB = "http://localhost:3000"
EMAIL = "smoke@example.com"  # on docker-compose.yml's SIGNUP_ALLOWED_EMAILS
PASSWORD = "compose-smoke-password"  # noqa: S105  fake, local stack only
SUITE = Path(__file__).resolve().parent.parent / "suites" / "examples" / "smoke.yaml"
AGENT = {
    "name": "support-v1",  # the smoke suite's `agent:`
    "config": {
        "adapter_type": "http",
        "url": "http://demo-agents:9000/support/v1/chat",
        "allow_private": True,
        "response": {
            "output": "$.output",
            "tool_calls": "$.tool_calls",
            "total_tokens": "$.usage.total_tokens",
        },
    },
}
RUN_TIMEOUT_S = 180
# The session cookies are Secure, and http.cookiejar never sends those over http://, so they are
# kept by hand. (Browsers treat localhost as a secure context and send them.)
cookies: dict[str, str] = {}


def request(method: str, url: str, body: Any = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310  localhost URLs
    req.add_header("Origin", WEB)  # the API's CSRF check on cookie sessions (ADR 0009)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            status, raw, headers = resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        status, raw, headers = exc.code, exc.read(), exc.headers
    except urllib.error.URLError as exc:
        sys.exit(f"FAIL {method} {url}: {exc.reason}")
    for cookie in headers.get_all("Set-Cookie") or []:
        name, _, rest = cookie.partition("=")
        cookies[name.strip()] = rest.split(";", 1)[0]
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode(errors="replace")[:500]


def api(method: str, path: str, body: Any = None) -> Any:
    status, payload = request(method, f"{WEB}/api{path}", body)
    if not 200 <= status < 300:
        sys.exit(f"FAIL {method} /api{path}: {status} {payload}")
    return payload


def main() -> None:
    for url in (f"{API}/health", f"{WEB}/login"):
        status, _ = request("GET", url)
        if status != 200:
            sys.exit(f"FAIL GET {url}: {status}")
        print(f"ok   GET {url}")

    credentials = {"email": EMAIL, "password": PASSWORD}
    status, payload = request("POST", f"{WEB}/api/auth/register", credentials)
    if status == 409:  # already registered: a rerun against the same database volume
        api("POST", "/auth/login", credentials)
    elif status != 201:
        sys.exit(f"FAIL POST /api/auth/register: {status} {payload}")
    print(f"ok   signed in as {EMAIL}")

    project = api("POST", "/projects", {"name": f"compose-smoke-{int(time.time())}"})
    api("POST", f"/projects/{project['id']}/agents", AGENT)
    suite = api(
        "POST", f"/projects/{project['id']}/suites", {"yaml": SUITE.read_text(encoding="utf-8")}
    )
    run = api("POST", f"/suites/{suite['id']}/runs", {})
    print(f"ok   run {run['id']} queued: {run['attempts_total']} attempts")

    deadline = time.monotonic() + RUN_TIMEOUT_S
    while run["status"] in ("queued", "running"):
        if time.monotonic() > deadline:
            sys.exit(f"FAIL run still {run['status']} after {RUN_TIMEOUT_S} s: {run}")
        time.sleep(1)
        run = api("GET", f"/runs/{run['id']}")
    rate = run["pass_rate"]
    if run["status"] != "completed" or not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
        sys.exit(f"FAIL run ended {run['status']} with pass_rate {rate!r}: {run}")
    print(f"ok   run completed: {run['attempts_done']} attempts, pass rate {rate:.2f}")


if __name__ == "__main__":
    main()
