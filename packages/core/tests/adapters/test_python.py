"""Python adapter (CLI only): loading `module:callable`, sync/async, str/dict results, and
refusing to load in a server process.
"""

import sys
import textwrap
import types
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from agentprobe_core.adapters import AdapterNotAllowed, build_adapter
from agentprobe_core.adapters.python import SERVER_PACKAGE, PythonAdapter
from agentprobe_core.adapters.types import ErrorStep, MessageStep, ToolCallStep, ToolResultStep

AGENT_SOURCE = textwrap.dedent(
    """
    import asyncio

    def echo(input):
        return f"echo: {input}"

    def with_context(input, context):
        return f"{input} | docs: {context}"

    async def async_echo(input):
        await asyncio.sleep(0)
        return f"async: {input}"

    def returns_awaitable(input):
        return async_echo(input)

    def with_steps(input):
        return {
            "output": "done",
            "steps": [
                {"type": "tool_call", "tool": "lookup", "arguments": {"id": 1}},
                {"type": "tool_result", "tool": "lookup", "result": {"ok": True}},
            ],
        }

    def boom(input):
        raise RuntimeError("agent crashed")

    async def slow(input):
        await asyncio.sleep(10)

    def bad_result(input):
        return {"answer": 1}

    class Bot:
        def run(self, input):
            return "method"

    bot = Bot()
    NOT_CALLABLE = 42
    """
)

Target = Callable[[str], str]


@pytest.fixture(autouse=True)
def not_in_server(monkeypatch: pytest.MonkeyPatch) -> None:
    # Other tests in this pytest process import the API; this module is about the CLI.
    monkeypatch.delitem(sys.modules, SERVER_PACKAGE, raising=False)


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Target:
    module = f"probe_agent_{uuid.uuid4().hex}"
    (tmp_path / f"{module}.py").write_text(AGENT_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return lambda attr: f"{module}:{attr}"


@pytest.mark.parametrize(
    ("attr", "output"),
    [
        ("echo", "echo: hi"),
        ("async_echo", "async: hi"),
        ("returns_awaitable", "async: hi"),
        ("bot.run", "method"),
        ("with_context", "hi | docs: ['d1', {'k': 'v'}]"),
    ],
)
async def test_calls_sync_and_async_callables(target: Target, attr: str, output: str) -> None:
    response = await PythonAdapter(target(attr)).invoke("hi", ["d1", {"k": "v"}])
    assert response.error is None
    assert response.output == output
    assert not response.tool_calls_reported
    user, assistant = response.steps
    assert isinstance(user, MessageStep) and user.content == "hi"
    assert isinstance(assistant, MessageStep) and assistant.content == output


async def test_dict_result_with_steps(target: Target) -> None:
    response = await PythonAdapter(target("with_steps")).invoke("hi")
    assert response.error is None
    assert response.tool_calls_reported
    assert [type(s) for s in response.steps] == [
        MessageStep,
        ToolCallStep,
        ToolResultStep,
        MessageStep,
    ]
    assert response.tool_calls[0].arguments == {"id": 1}


@pytest.mark.parametrize(
    ("attr", "message"),
    [
        ("boom", "RuntimeError: agent crashed"),
        ("bad_result", "invalid result"),
    ],
)
async def test_agent_failures_are_error_responses(target: Target, attr: str, message: str) -> None:
    response = await PythonAdapter(target(attr)).invoke("hi")
    assert response.error is not None
    assert message in response.error
    assert response.output == ""
    assert isinstance(response.steps[-1], ErrorStep)


async def test_timeout(target: Target) -> None:
    response = await PythonAdapter(target("slow"), timeout_s=0.05).invoke("hi")
    assert response.error == "no result within 0.05s"


@pytest.mark.parametrize(
    ("spec", "error"),
    [
        ("no_colon", ValueError),
        ("mod:", ValueError),
        ("os.system; rm:x", ValueError),
        ("definitely_not_a_module_x9:run", ModuleNotFoundError),
    ],
)
def test_bad_targets(spec: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        PythonAdapter(spec)


def test_missing_or_non_callable_attribute(target: Target) -> None:
    with pytest.raises(AttributeError):
        PythonAdapter(target("nope"))
    with pytest.raises(TypeError, match="not callable"):
        PythonAdapter(target("NOT_CALLABLE"))


# --- the server can't load it ---------------------------------------------------------------


def test_refuses_to_load_in_a_server_process(
    target: Target, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, SERVER_PACKAGE, types.ModuleType(SERVER_PACKAGE))
    spec = target("echo")
    with pytest.raises(AdapterNotAllowed, match="CLI-only"):
        PythonAdapter(spec)
    assert spec.partition(":")[0] not in sys.modules  # the user's code never ran


def test_build_adapter_refuses_python() -> None:
    with pytest.raises(AdapterNotAllowed, match="CLI-only"):
        build_adapter("python", {"module": "os", "function": "system"})
    with pytest.raises(AdapterNotAllowed, match="not supported"):
        build_adapter("mcp", {"server_url": "https://mcp.example.com"})
