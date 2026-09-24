"""Python adapter: calls a local `module:callable` in-process (SPEC.md §4.2). CLI only.

Loading it imports and runs arbitrary code, so the server must never do it (PLAN.md §2 #14):
`agentprobe_core.adapters` doesn't import this module, `build_adapter` refuses `python`, the
API rejects python configs, and as a backstop the adapter refuses to load in any process that
has imported the API server package.

The callable takes `(input)` or `(input, context)`, may be sync or async, and returns either
the output string or `{"output": str, "steps": [TraceStep, ...]}`.
"""

import asyncio
import importlib
import inspect
import re
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from agentprobe_core.adapters.types import (
    AdapterNotAllowed,
    AgentResponse,
    ErrorStep,
    MessageStep,
    TraceStep,
)

SERVER_PACKAGE = "agentprobe_api"
_TARGET = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: str
    steps: list[TraceStep] = Field(default_factory=list)


def load_callable(target: str) -> Callable[..., Any]:
    """Imports `module:attr.path`. Import errors propagate as they are, for the CLI to show."""
    if SERVER_PACKAGE in sys.modules:
        raise AdapterNotAllowed("the python adapter is CLI-only; the server can't load it")
    if not _TARGET.fullmatch(target):
        raise ValueError(f"expected 'module:callable' (e.g. 'my_agent:run'), got {target!r}")
    module_name, _, attr_path = target.partition(":")
    obj: Any = importlib.import_module(module_name)
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    if not callable(obj):
        raise TypeError(f"{target} is not callable")
    return obj  # type: ignore[no-any-return]


def _accepts_context(fn: Callable[..., Any]) -> bool:
    try:
        inspect.signature(fn).bind("", [])
    except (TypeError, ValueError):
        return False
    return True


class PythonAdapter:
    def __init__(self, target: str, *, timeout_s: float = 30.0) -> None:
        self._fn = load_callable(target)
        self._pass_context = _accepts_context(self._fn)
        self._timeout_s = timeout_s

    async def invoke(self, input: str, context: Sequence[JsonValue] = ()) -> AgentResponse:
        started, t0 = datetime.now(UTC), time.perf_counter()
        steps: list[TraceStep] = [MessageStep(role="user", content=input, timestamp=started)]
        args = (input, list(context)) if self._pass_context else (input,)
        try:
            async with asyncio.timeout(self._timeout_s):
                if inspect.iscoroutinefunction(self._fn):
                    result = await self._fn(*args)
                else:
                    # ponytail: a hung sync callable keeps its worker thread after the timeout
                    # (threads can't be cancelled); run it in a subprocess if that matters.
                    result = await asyncio.to_thread(self._fn, *args)
                    if inspect.isawaitable(result):
                        result = await result
            if isinstance(result, str):
                result = {"output": result}
            parsed = _Result.model_validate(result)
        except TimeoutError:
            error = f"no result within {self._timeout_s:g}s"
        except ValidationError as exc:
            error = f"invalid result (want str or {{output, steps}}): {exc.error_count()} error(s)"
        except Exception as exc:  # the agent's own failure is a result, not a crash
            error = f"{type(exc).__name__}: {exc}"[:500]
        else:
            latency_ms = (time.perf_counter() - t0) * 1000
            return AgentResponse(
                output=parsed.output,
                steps=[
                    *steps,
                    *parsed.steps,
                    MessageStep(
                        role="assistant",
                        content=parsed.output,
                        timestamp=started,
                        duration_ms=latency_ms,
                    ),
                ],
                latency_ms=latency_ms,
                tool_calls_reported="steps" in result,
            )
        latency_ms = (time.perf_counter() - t0) * 1000
        steps.append(ErrorStep(message=error, timestamp=started, duration_ms=latency_ms))
        return AgentResponse(output="", steps=steps, latency_ms=latency_ms, error=error)
