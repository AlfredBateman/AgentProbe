"""Does AgentProbe detect the demo agents' planted flaws? The one definition of "detected",
shared by the golden tests (demo-agents/tests/test_golden.py) and
scripts/measure_detection.py.

Every flaw in vulnerabilities.json names a suite, the case(s) that target it, the label a
detection should produce, and a negative control: the same case(s) on an agent that doesn't
have the flaw, which must pass. The suites run for real, through core's `run_suite` and the
HTTP adapter, against the demo agents at `base_url`.

- A flaw is **detected** when every listed case has at least one attempt a judge failed
  (errors don't count: an agent that crashed was not caught misbehaving). A regression flaw
  (`baseline_route`) must also get a `regression` verdict naming its case(s) against the
  baseline run, since that is what AgentProbe reports for a regression.
- `as_expected` is the stricter golden-test check: every listed case got exactly the
  manifest's `expected` label.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agentprobe_core.adapters import HttpAdapter, HttpAdapterConfig, TargetPolicy
from agentprobe_core.llm.types import LLMClient
from agentprobe_core.runner import AttemptResult, CaseResult, RunOptions, RunSummary, run_suite
from agentprobe_core.stats import compare_runs
from agentprobe_core.suite import parse_suite_yaml
from agentprobe_core.suite.schema import Suite

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "demo-agents" / "vulnerabilities.json"

SUPPORT_RESPONSE = {"tool_calls": "$.tool_calls", "total_tokens": "$.usage.total_tokens"}
RAG_RESPONSE = {
    "output": "$.result.text",
    "input_tokens": "$.meta.tokens.input",
    "output_tokens": "$.meta.tokens.output",
}

RunKey = tuple[str, str]  # (suite path relative to the repo root, agent route)


@dataclass(frozen=True)
class Control:
    route: str
    case_ids: tuple[str, ...]
    note: str | None = None


@dataclass(frozen=True)
class Flaw:
    id: str
    route: str
    category: str
    description: str
    suite: str
    case_ids: tuple[str, ...]
    expected: str  # the label a detection produces: "stable-fail" or "flaky"
    control: Control
    baseline_route: str | None = None  # set for a regression: compared against this route


@dataclass(frozen=True)
class FlawResult:
    flaw: Flaw
    detected: bool
    as_expected: bool
    labels: dict[str, str]  # listed case -> its label on the flaw's agent
    reason: str  # how it was detected, or why it wasn't
    control_passed: bool
    control_reason: str


def load_manifest(path: Path = MANIFEST_PATH) -> list[Flaw]:
    flaws = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        control = entry["negative_control"]
        flaws.append(
            Flaw(
                id=entry["id"],
                route=entry["route"],
                category=entry["category"],
                description=entry["description"],
                suite=entry["suite"],
                case_ids=tuple(entry["suite_case_ids"]),
                expected=entry["expected"],
                control=Control(control["route"], tuple(control["case_ids"]), control.get("note")),
                baseline_route=entry.get("baseline_route"),
            )
        )
    return flaws


def required_runs(flaws: Sequence[Flaw]) -> list[RunKey]:
    """Each (suite, route) run the manifest needs once: flaws, baselines and controls."""
    keys: dict[RunKey, None] = {}  # ordered set
    for flaw in flaws:
        keys[(flaw.suite, flaw.route)] = None
        if flaw.baseline_route is not None:
            keys[(flaw.suite, flaw.baseline_route)] = None
        keys[(flaw.suite, flaw.control.route)] = None
    return list(keys)


def load_suite(path: str) -> Suite:
    return parse_suite_yaml((REPO_ROOT / path).read_text(encoding="utf-8"))


def adapter_for(base_url: str, route: str, *, timeout_ms: int = 30_000) -> HttpAdapter:
    config = HttpAdapterConfig.model_validate(
        {
            "url": f"{base_url}{route}/chat",
            "allow_private": True,  # the demo agents run on loopback
            "response": RAG_RESPONSE if route == "/rag" else SUPPORT_RESPONSE,
            "timeout_ms": timeout_ms,
        }
    )
    return HttpAdapter(config, policy=TargetPolicy(allow_private=True))


async def run_one(
    base_url: str,
    key: RunKey,
    options: RunOptions = RunOptions(),  # noqa: B008 (frozen dataclass)
    *,
    llm: LLMClient | None = None,
    timeout_ms: int = 30_000,
    completed: Sequence[AttemptResult] = (),
    on_result: Callable[[AttemptResult], Awaitable[None]] | None = None,
    cancel: asyncio.Event | None = None,
) -> RunSummary:
    suite_path, route = key
    async with adapter_for(base_url, route, timeout_ms=timeout_ms) as adapter:
        return await run_suite(
            load_suite(suite_path),
            adapter,
            llm,
            options,
            agent=route,
            completed=completed,
            on_result=on_result,
            cancel=cancel,
        )


def _case(run: RunSummary, case_id: str) -> CaseResult | None:
    return next((case for case in run.cases if case.case_id == case_id), None)


def _failed(case: CaseResult) -> int:
    summary = case.summary
    return summary.attempts - summary.passes - summary.errors


def _judges(case: CaseResult) -> str:
    """The failing judges' names (or error kinds), never their reasons: those quote agent
    output, which is untrusted and ends up in docs/metrics.md.
    """
    names = dict.fromkeys(failure.split(":", 1)[0] for failure in case.failures)
    return ", ".join(names) or "no judge failed"


def _detection(flaw: Flaw, runs: Mapping[RunKey, RunSummary]) -> tuple[bool, str]:
    run = runs[(flaw.suite, flaw.route)]
    parts = []
    for case_id in flaw.case_ids:
        case = _case(run, case_id)
        if case is None:
            return False, f"{case_id} is not in {flaw.suite}"
        summary = case.summary
        if _failed(case) == 0:
            reason = f"{case_id} passed {summary.passes}/{summary.attempts}"
            if summary.errors:
                reason += f", {summary.errors} errored ({_judges(case)})"
            return False, reason
        parts.append(f"{_failed(case)}/{summary.attempts} attempts failed: {_judges(case)}")

    if flaw.baseline_route is not None:
        baseline = runs[(flaw.suite, flaw.baseline_route)]
        report = compare_runs(baseline.case_summaries(), run.case_summaries(), run.statistics)
        compared = {c.case_id: c for c in report.cases if c.case_id in flaw.case_ids}
        stats = []
        for case_id in flaw.case_ids:
            comparison = compared.get(case_id)
            if comparison is None:
                return False, f"{case_id} is not in the {flaw.baseline_route} baseline run"
            threshold = comparison.p_worse_threshold
            stat = f"{case_id}: p = {comparison.p_worse:.4f}, threshold " + (
                f"{threshold:.4f}" if threshold is not None else "not reached"
            )
            if not comparison.regressed or report.verdict != "regression":
                return False, (
                    f"{case_id} fails, but the verdict against {flaw.baseline_route} is "
                    f"{report.verdict} ({stat})"
                )
            stats.append(stat)
        return True, f"regression against {flaw.baseline_route} ({'; '.join(stats)})"
    return True, "; ".join(parts)


def _control(flaw: Flaw, runs: Mapping[RunKey, RunSummary]) -> tuple[bool, str]:
    run = runs[(flaw.suite, flaw.control.route)]
    problems = []
    for case_id in flaw.control.case_ids:
        case = _case(run, case_id)
        if case is None:
            problems.append(f"{case_id} is not in {flaw.suite}")
        elif case.label != "stable-pass":
            summary = case.summary
            problems.append(
                f"{case_id} passed {summary.passes}/{summary.attempts} on {flaw.control.route}"
                f" ({_judges(case)})"
            )
    if problems:
        return False, "; ".join(problems)
    return True, f"{', '.join(flaw.control.case_ids)} passed on {flaw.control.route}"


def evaluate(flaws: Sequence[Flaw], runs: Mapping[RunKey, RunSummary]) -> list[FlawResult]:
    results = []
    for flaw in flaws:
        run = runs[(flaw.suite, flaw.route)]
        labels: dict[str, str] = {}
        for case_id in flaw.case_ids:
            case = _case(run, case_id)
            labels[case_id] = case.label if case is not None else "missing"
        detected, reason = _detection(flaw, runs)
        control_passed, control_reason = _control(flaw, runs)
        results.append(
            FlawResult(
                flaw=flaw,
                detected=detected,
                as_expected=all(label == flaw.expected for label in labels.values()),
                labels=labels,
                reason=reason,
                control_passed=control_passed,
                control_reason=control_reason,
            )
        )
    return results
