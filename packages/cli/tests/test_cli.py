"""CliRunner tests for every command, offline: agents are in-process Python callables
(`cli_agents`), except the one test that needs an unreachable HTTP agent.
"""

import functools
import json
import re
import socket
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from agentprobe import main, push, report
from agentprobe.config import load_config
from agentprobe.main import app
from agentprobe_core.suite import parse_suite_yaml

runner = CliRunner()

CONFIG = {
    "agents": {
        "good": {"type": "python", "target": "cli_agents:good"},
        "bad": {"type": "python", "target": "cli_agents:bad"},
        "hostile": {"type": "python", "target": "cli_agents:hostile"},
        "tools": {"type": "python", "target": "cli_agents:with_tools"},
    },
    "run": {"retries": 0},
}


def suite(**overrides: Any) -> dict[str, Any]:
    return {
        "suite": "cli",
        "agent": "good",
        "runs_per_case": 3,
        "cases": [
            {"id": "a", "input": "one", "expect": [{"judge": "contains", "value": "ok"}]},
            {"id": "b", "input": "two", "expect": [{"judge": "max_length", "max_chars": 100}]},
        ],
        **overrides,
    }


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTPROBE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    # The Python adapter refuses to load in a process that imported the API server (ADR
    # 0012); in the shared pytest process the api tests have. A real CLI process never has.
    monkeypatch.delitem(sys.modules, "agentprobe_api", raising=False)
    (tmp_path / "agentprobe.yaml").write_text(yaml.safe_dump(CONFIG))
    write_suite(suite())
    return tmp_path


def write_suite(data: dict[str, Any], name: str = "suite.yaml") -> str:
    Path(name).write_text(yaml.safe_dump(data))
    return name


def invoke(*args: str) -> Any:
    return runner.invoke(app, list(args))


def runs() -> list[Path]:
    return sorted(Path("state/runs").glob("*.json"))


# --- help ----------------------------------------------------------------------------------


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def help_text(*args: str) -> str:
    """`--help` as one line, ANSI stripped and wrapping undone.

    Rich wraps help to the terminal width, so asserting a literal phrase against the raw
    output passes or fails depending on where the break happens to land: "Small-N limit"
    survives at 80 columns and splits at 81, which is how a green local run became a red CI
    run. The phrases below are about content, so the wrapping is normalized away.
    """
    result = invoke(*args, "--help")
    assert result.exit_code == 0, result.output
    return " ".join(_ANSI.sub("", result.output).split())


def test_help_documents_exit_codes() -> None:
    top = help_text()
    for line in ("0 passed", "1 pass rate below", "2 regression", "3 usage", "4 infra"):
        assert line in top
    run_help = help_text("run")
    assert "Exit codes" in run_help
    # ADR 0006 requires the small-N limit in --help, and ADR 0014's alpha split changed what
    # it says: 3 runs per case can no longer flag a case at all.
    assert "Small-N limit" in run_help
    assert "--alpha is the budget for both together" in run_help
    assert "at 3 runs it can never be flagged" in run_help


# --- init ----------------------------------------------------------------------------------


def test_init_scaffolds_a_config_and_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "fresh"
    empty.mkdir()
    monkeypatch.chdir(empty)
    result = invoke("init")
    assert result.exit_code == 0, result.output
    assert load_config(empty / "agentprobe.yaml").agents["my-agent"].type == "http"
    example = parse_suite_yaml((empty / "suites/example.yaml").read_text())
    assert example.agent == "my-agent"

    again = invoke("init")
    assert again.exit_code == 3
    assert "already exist" in again.output
    assert invoke("init", "--force").exit_code == 0


# --- run -----------------------------------------------------------------------------------


def test_run_passes_and_saves_the_full_result() -> None:
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 0, result.output
    assert "Pass rate 100.0%" in result.output
    assert "stable-pass" in result.output
    [saved] = runs()
    data = json.loads(saved.read_text())
    assert data["suite"] == "cli"
    assert len(data["results"]) == 6
    first = data["results"][0]
    assert first["input"] == "one"
    assert first["response"]["steps"][0]["type"] == "message"
    assert first["judgments"][0]["judge"] == "contains"


def test_run_below_threshold_exits_1() -> None:
    result = invoke("run", "suite.yaml", "--agent", "bad")
    assert result.exit_code == 1
    assert "Failing cases" in result.output
    assert "contains: output does not contain 'ok'" in result.output
    assert "THRESHOLD (exit 1)" in result.output
    assert invoke("run", "suite.yaml", "--agent", "bad", "--fail-under", "0.5").exit_code == 0
    assert invoke("run", "suite.yaml", "--agent", "bad", "--fail-under", "0.51").exit_code == 1


def test_run_json_output() -> None:
    result = invoke("run", "suite.yaml", "--json", "--runs-per-case", "2")
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == 0
    assert payload["regression"] is None
    assert Path(payload["file"]).is_file()
    run = payload["run"]
    assert (run["runs_per_case"], run["attempts"], run["pass_rate"]) == (2, 4, 1.0)
    assert [c["label"] for c in run["cases"]] == ["stable-pass", "stable-pass"]


def test_tool_calls_are_traced_and_judged() -> None:
    write_suite(
        suite(
            agent="tools",
            cases=[
                {
                    "id": "delete",
                    "input": "x",
                    "expect": [{"judge": "tool_not_called", "tool": "delete_order"}],
                }
            ],
        )
    )
    result = invoke("run", "suite.yaml", "--json")
    assert result.exit_code == 1
    [attempt, *_] = json.loads(result.stdout)["run"]["results"]
    [call] = [s for s in attempt["response"]["steps"] if s["type"] == "tool_call"]
    assert (call["tool"], call["arguments"]) == ("delete_order", {"id": "1"})


def test_mock_flag_forces_the_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    rubric = {"judge": "llm_rubric", "rubric": "The answer is polite."}
    write_suite(suite(cases=[{"id": "r", "input": "hi", "expect": [rubric]}]))
    monkeypatch.setenv("LLM_PROVIDER", "litellm")
    monkeypatch.delenv("RUN_LIVE", raising=False)
    refused = invoke("run", "suite.yaml")
    assert refused.exit_code == 3
    assert "LLM provider" in refused.output  # live needs RUN_LIVE and config/llm.yaml
    result = invoke("run", "suite.yaml", "--mock", "--json")
    assert result.exit_code in (0, 1)  # the mock judge's verdict; the point is no live call
    [attempt, *_] = json.loads(result.stdout)["run"]["results"]
    assert attempt["judgments"][0]["judge"] == "llm_rubric"
    assert attempt["error"] is None


def test_agent_output_cannot_inject_markup_or_escape_codes() -> None:
    result = invoke("run", "suite.yaml", "--agent", "hostile")
    assert result.exit_code == 1
    assert "[bold red]PWNED[/bold red]" in result.output  # shown literally
    assert "\x1b[2J" not in result.output


def test_suite_name_never_escapes_the_runs_directory() -> None:
    write_suite(suite(suite="../../escape"))
    assert invoke("run", "suite.yaml").exit_code == 0
    [saved] = runs()
    assert saved.parent == Path("state/runs")
    assert "escape" in saved.name


# --- usage errors: exit 3 ------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["run", "missing.yaml"],
        ["run", "suite.yaml", "--agent", "nobody"],
        ["run", "suite.yaml", "--config", "nope.yaml"],
        ["run", "suite.yaml", "--runs-per-case", "0"],
        ["run", "suite.yaml", "--alpha", "2"],
        ["run", "suite.yaml", "--baseline", "nothing-saved"],
        ["run", "suite.yaml", "--no-such-flag"],
        ["run"],
        ["compare", "a.json"],
        ["frobnicate"],
    ],
)
def test_usage_errors_exit_3(args: list[str]) -> None:
    result = invoke(*args)
    assert result.exit_code == 3, result.output


def test_an_invalid_suite_shows_linter_style_issues() -> None:
    write_suite({"suite": "x", "agent": "good", "cases": [{"id": "a", "input": "b"}]})
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 3
    assert "cases.0.expect" in result.output


def test_an_invalid_config_is_a_usage_error() -> None:
    Path("agentprobe.yaml").write_text("agents: {x: {type: ftp}}")
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 3
    assert "agents.x" in result.output


def test_an_unloadable_python_agent_is_a_usage_error() -> None:
    config = {"agents": {"good": {"type": "python", "target": "no_such_module_xyz:run"}}}
    Path("agentprobe.yaml").write_text(yaml.safe_dump(config))
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 3
    assert "no_such_module_xyz" in result.output


def test_a_missing_secret_header_env_var_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLI_TEST_TOKEN", raising=False)
    config = {
        "agents": {
            "good": {
                "type": "http",
                "url": "http://127.0.0.1:1/chat",
                "secret_headers_env": {"Authorization": "CLI_TEST_TOKEN"},
            }
        }
    }
    Path("agentprobe.yaml").write_text(yaml.safe_dump(config))
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 3
    assert "CLI_TEST_TOKEN" in result.output


def test_an_attack_id_without_an_input_is_a_suite_error() -> None:
    case = {"id": "a", "attack": "tool_misuse", "expect": [{"judge": "contains", "value": "x"}]}
    write_suite(suite(cases=[case]))
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 3
    # Rich wraps the error to the terminal width; match the words, not the line breaks.
    assert "a case needs `input` or `call`" in " ".join(result.output.split())
    assert runs() == []


# --- infrastructure errors: exit 4 ---------------------------------------------------------


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def test_an_unreachable_agent_exits_4() -> None:
    config = {
        "agents": {
            "good": {
                "type": "http",
                "url": f"http://127.0.0.1:{closed_port()}/chat",
                "allow_private": True,
                "max_retries": 0,
            }
        },
        "run": {"retries": 0, "concurrency": 1},
    }
    Path("agentprobe.yaml").write_text(yaml.safe_dump(config))
    result = invoke("run", "suite.yaml")  # 2 cases x 3 runs
    assert result.exit_code == 4, result.output
    assert "unreachable error: could not connect" in result.output
    assert "INFRA (exit 4)" in result.output
    # it stops at the first infrastructure error instead of retrying all 6 attempts
    assert "Stopped early" in result.output
    [saved] = runs()
    data = json.loads(saved.read_text())
    assert data["status"] == "cancelled"
    assert data["attempts"] == 1


def test_a_private_agent_without_opt_in_is_blocked() -> None:
    config = {"agents": {"good": {"type": "http", "url": "http://127.0.0.1:9/chat"}}}
    Path("agentprobe.yaml").write_text(yaml.safe_dump(config))
    write_suite(suite(runs_per_case=1))
    result = invoke("run", "suite.yaml")
    assert result.exit_code == 1  # an agent error (blocked target), not a reachable pass
    assert "allow_private" in result.output or "private" in result.output


# --- baselines and compare -----------------------------------------------------------------


def test_baseline_regression_exits_2() -> None:
    write_suite(suite(runs_per_case=5))
    assert invoke("run", "suite.yaml").exit_code == 0
    [first] = runs()
    set_result = invoke("baseline", "set", str(first))
    assert set_result.exit_code == 0, set_result.output
    assert Path("state/baselines/main.json").is_file()

    same = invoke("run", "suite.yaml", "--baseline", "main")
    assert same.exit_code == 0, same.output
    assert "no change" in same.output

    worse = invoke("run", "suite.yaml", "--agent", "bad", "--baseline", "main", "--fail-under", "0")
    assert worse.exit_code == 2, worse.output
    assert "regressed a: 5/5 -> 0/5" in worse.output
    # regression wins over a missed threshold
    assert invoke("run", "suite.yaml", "--agent", "bad", "--baseline", "main").exit_code == 2
    # by file path too, and in the JSON output
    as_json = invoke("run", "suite.yaml", "--agent", "bad", "--baseline", str(first), "--json")
    assert json.loads(as_json.stdout)["regression"]["verdict"] == "regression"


def test_a_json_output_file_works_as_a_baseline() -> None:
    # The Action's `result-file` is `run --json` output; the dogfood workflow keeps it as the
    # next PR's baseline (it was once rejected as "not an AgentProbe run file").
    write_suite(suite(runs_per_case=5))
    wrapped = invoke("run", "suite.yaml", "--json")
    assert wrapped.exit_code == 0, wrapped.output
    Path("result.json").write_text(wrapped.stdout)
    same = invoke("run", "suite.yaml", "--baseline", "result.json")
    assert same.exit_code == 0, same.output
    assert "no change" in same.output
    worse = invoke(
        "run", "suite.yaml", "--agent", "bad", "--baseline", "result.json", "--fail-under", "0"
    )
    assert worse.exit_code == 2, worse.output
    Path("result.json").write_text("not json")
    broken = invoke("run", "suite.yaml", "--baseline", "result.json")
    assert broken.exit_code == 3
    assert "not an AgentProbe run file" in broken.output


def test_a_tiny_p_value_is_not_printed_as_zero() -> None:
    assert report.p_value(5.4e-6) == "5.4e-06"
    assert report.p_value(0.0125) == "0.0125"
    assert report.p_value(0.0) == "0.0000"
    assert report.p_value(1.0) == "1.0000"


def test_baseline_must_be_the_same_suite() -> None:
    assert invoke("run", "suite.yaml").exit_code == 0
    [first] = runs()
    assert invoke("baseline", "set", str(first), "--name", "v1").exit_code == 0
    write_suite(suite(suite="other"))
    result = invoke("run", "suite.yaml", "--baseline", "v1")
    assert result.exit_code == 3
    assert "suite 'cli'" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["baseline", "set", "missing.json"],
        ["baseline", "set", "suite.yaml"],  # not a run file
        ["baseline", "set", "RUN", "--name", "../evil"],
    ],
)
def test_baseline_set_rejects_bad_input(args: list[str]) -> None:
    assert invoke("run", "suite.yaml").exit_code == 0
    [first] = runs()
    result = invoke(*[str(first) if a == "RUN" else a for a in args])
    assert result.exit_code == 3, result.output
    # --name ../evil would land beside baselines/, in the state dir
    assert not Path("state/evil.json").exists()
    assert not list(Path("state/baselines").glob("*.json"))  # nothing saved at all


# --- --push (the server side is covered in apps/api/tests/test_ci_report.py) ---------------


def fake_server(
    monkeypatch: pytest.MonkeyPatch, respond: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(main, "push_run", functools.partial(push.push, transport=transport))
    monkeypatch.setattr(main, "fetch_run", functools.partial(push.fetch, transport=transport))
    monkeypatch.setenv(push.URL_ENV, "https://ap.test/")
    monkeypatch.setenv(push.KEY_ENV, "ap_fake-key")  # fake credential
    return seen


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def test_push_sends_a_python_agent_by_name_and_a_remote_regression_exits_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = {"run_id": "r1", "verdict": "regression", "comparison": {"regressed": ["a"]}}
    seen = fake_server(monkeypatch, lambda _: httpx.Response(201, json=reply))
    args = ["--branch", "pr-7", "--baseline-branch", "main", "--pr", "7", "--model", "m-2"]
    result = invoke("run", "suite.yaml", "--push", *args)
    assert result.exit_code == 2, result.output  # passed locally, regressed on the server
    assert "regressed: a" in result.output
    [request] = seen
    assert str(request.url) == "https://ap.test/ci/report"
    assert request.headers["authorization"] == "Bearer ap_fake-key"
    body = json.loads(request.content)
    assert "agent" not in body  # a python agent can't be registered on the server
    assert (body["suite"], body["agent_name"], body["runs_per_case"]) == ("cli", "good", 3)
    assert (body["branch"], body["baseline_branch"], body["pr_number"]) == ("pr-7", "main", 7)
    assert (body["model"], body["mock"], len(body["results"])) == ("m-2", True, 6)


@pytest.mark.parametrize(
    ("respond", "code", "message"),
    [
        (lambda _: httpx.Response(422, json={"error": {"message": "no suite"}}), 3, "no suite"),
        (lambda _: httpx.Response(503, text="down"), 4, "HTTP 503"),
        (unreachable, 4, "can't reach https://ap.test"),
    ],
    ids=["refused", "server-error", "unreachable"],
)
def test_push_failures_map_to_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[httpx.Request], httpx.Response],
    code: int,
    message: str,
) -> None:
    fake_server(monkeypatch, respond)
    result = invoke("run", "suite.yaml", "--push", "--branch", "main")
    assert result.exit_code == code, result.output
    assert message in result.output
    assert len(runs()) == 1  # the local run is saved either way


@pytest.mark.parametrize("unset", [push.URL_ENV, push.KEY_ENV, "--branch"])
def test_push_is_checked_before_running(monkeypatch: pytest.MonkeyPatch, unset: str) -> None:
    seen = fake_server(monkeypatch, lambda _: httpx.Response(500))
    args = ["run", "suite.yaml", "--push"]
    if unset == "--branch":
        result = invoke(*args)
    else:
        monkeypatch.delenv(unset)
        result = invoke(*args, "--branch", "main")
    assert result.exit_code == 3, result.output
    assert unset in result.output
    assert (seen, runs()) == ([], [])  # nothing ran, nothing was sent


def test_push_with_an_unresolvable_baseline_explains_both_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = fake_server(monkeypatch, lambda _: httpx.Response(500))
    result = invoke("run", "suite.yaml", "--push", "--branch", "pr-7", "--baseline", "main")
    assert result.exit_code == 3, result.output
    out = " ".join(result.output.split())  # Rich wraps at the terminal width
    assert "--baseline compares locally" in out
    assert "--baseline-branch compares on the server" in out
    assert "pass --baseline-branch main instead" in out
    assert (seen, runs()) == ([], [])
    # without --push, or with --baseline-branch given, it's the plain not-found error
    for args in ([], ["--push", "--branch", "pr-7", "--baseline-branch", "main"]):
        plain = invoke("run", "suite.yaml", "--baseline", "main", *args)
        assert plain.exit_code == 3, plain.output
        assert "no such run file or baseline name" in plain.output
        assert "--baseline-branch compares" not in " ".join(plain.output.split())


def test_compare_prints_the_diff_and_exits_2_on_regression() -> None:
    write_suite(suite(runs_per_case=5))
    good = json.loads(invoke("run", "suite.yaml", "--json").stdout)["file"]
    bad = json.loads(invoke("run", "suite.yaml", "--agent", "bad", "--json").stdout)["file"]
    result = invoke("compare", str(good), str(bad))
    assert result.exit_code == 2, result.output
    assert "REGRESSED" in result.output
    assert "newly failing: a" in result.output
    improved = invoke("compare", str(bad), str(good))
    assert improved.exit_code == 0
    assert "improvement" in improved.output
    assert invoke("compare", str(good), str(good)).exit_code == 0
    assert invoke("compare", str(good), "nope.json").exit_code == 3
    assert invoke("compare", str(good), str(bad), "--alpha", "0").exit_code == 3


def test_compare_and_baseline_accept_a_server_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    write_suite(suite(runs_per_case=5))
    good = json.loads(invoke("run", "suite.yaml", "--json").stdout)["run"]
    bad_path = json.loads(invoke("run", "suite.yaml", "--agent", "bad", "--json").stdout)["file"]
    run_id = str(uuid.uuid4())

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/runs/{run_id}/export"
        assert dict(request.url.params) == {"format": "json"}
        assert request.headers["authorization"] == "Bearer ap_fake-key"
        return httpx.Response(200, json={"run": {}, "summary": good})

    seen = fake_server(monkeypatch, respond)
    result = invoke("compare", run_id, bad_path)
    assert result.exit_code == 2, result.output
    assert "newly failing: a" in result.output
    assert len(seen) == 1  # only the server-id side is fetched

    via_baseline = invoke("run", "suite.yaml", "--agent", "bad", "--baseline", run_id)
    assert via_baseline.exit_code == 2, via_baseline.output


@pytest.mark.parametrize(
    ("respond", "code", "message"),
    [
        (lambda _: httpx.Response(422, json={"error": {"message": "no such run"}}), 3, "no such"),
        (lambda _: httpx.Response(503, text="down"), 4, "HTTP 503"),
        (unreachable, 4, "can't reach https://ap.test"),
    ],
    ids=["refused", "server-error", "unreachable"],
)
def test_compare_fetch_failures_map_to_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[httpx.Request], httpx.Response],
    code: int,
    message: str,
) -> None:
    fake_server(monkeypatch, respond)
    result = invoke("compare", str(uuid.uuid4()), "suite.yaml")  # never reaches the 2nd load
    assert result.exit_code == code, result.output
    assert message in result.output


def test_a_server_run_id_needs_the_push_env_vars() -> None:
    result = invoke("compare", str(uuid.uuid4()), "suite.yaml")
    assert result.exit_code == 3, result.output
    assert push.URL_ENV in result.output
