"""Does AgentProbe detect the demo agents' planted vulnerabilities? (SPEC.md §15)

    uv run python scripts/measure_detection.py                          # mock mode
    RUN_LIVE=1 uv run --env-file .env python scripts/measure_detection.py --live [--runs-per-case 3]

Runs every suite demo-agents/vulnerabilities.json names against the real demo agents (served
by this process on a free local port) through core's `run_suite`, then writes "Detected X of
Y ..." and a per-flaw table into docs/metrics.md. Mock and live results each own a marked
section there, so one never overwrites the other. What "detected" means is defined once, in
`agentprobe_demo_agents.detection`, and shared with the golden tests.

Mock mode: the demo agents' deterministic rule engine (AGENT_MODE=mock) and the mock LLM.
Offline; a few seconds.

Live mode (needs RUN_LIVE=1): the demo agents answer with a live model (AGENT_MODE=llm) and
any LLM judge in the suites is live too. It prints the estimated call count against the
configured daily limit and asks before spending anything. It runs one call at a time. Each
finished attempt is checkpointed to <AGENTPROBE_STATE_DIR>/detection-live.json, so a run that
stops (daily quota, budget, an error) resumes where it left off when started again, on
another day if need be; delete the file to start over. Attempts are checkpointed instead of
replayed from the LLM response cache on purpose: the cache keys on the prompt, so every
repeat of a case would get attempt 1's answer back, erasing the variance that running each
case several times exists to measure.

Numbers come only from these runs. Nothing here tunes an agent or a judge.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

from agentprobe_core.llm import create_client
from agentprobe_core.llm.config import LLMConfig
from agentprobe_core.llm.limits import DailyQuota, SystemClock
from agentprobe_core.llm.types import LLMClient
from agentprobe_core.runner import AttemptError, AttemptResult, RunOptions, RunSummary, uses_llm
from agentprobe_core.suite.schema import Suite
from agentprobe_demo_agents import flaky
from agentprobe_demo_agents.detection import (
    REPO_ROOT,
    Flaw,
    FlawResult,
    RunKey,
    evaluate,
    load_manifest,
    load_suite,
    required_runs,
    run_one,
)
from agentprobe_demo_agents.main import serve_in_background

METRICS = REPO_ROOT / "docs" / "metrics.md"
LIVE_RUNS_PER_CASE = 3
LIVE_TIMEOUT_MS = 120_000  # a call can wait out a whole RPM window before it's sent


# --- estimating and checkpointing a live run --------------------------------------------


def planned(suite: Suite, runs_per_case: int | None) -> int:
    return runs_per_case or suite.runs_per_case


def estimate(
    suites: Mapping[str, Suite],
    keys: Sequence[RunKey],
    runs_per_case: int | None,
    done: Mapping[RunKey, Sequence[AttemptResult]],
) -> tuple[int, int]:
    """(agent calls, judge calls) still to make. Every demo agent calls the model once per
    attempt in llm mode; judges once per llm_rubric sample per attempt (plus at most one
    repair retry each, not counted) and one embedding call per consistency judge per case.
    """
    agent = judge = 0
    for key in keys:
        suite = suites[key[0]]
        finished = {(r.case_id, r.attempt) for r in done.get(key, ())}
        for case in suite.cases:
            for n in range(planned(suite, runs_per_case)):
                if (case.id, n) in finished:
                    continue
                agent += 1
                judge += sum(s.samples for s in case.expect if s.judge == "llm_rubric")
            judge += sum(1 for s in case.expect if s.judge == "consistency")
    return agent, judge


class Checkpoint:
    """Finished live attempts, keyed by the agent and judge models, suite and route."""

    def __init__(self, path: Path, model: str) -> None:
        self.path, self.model = path, model
        try:
            self.data: dict[str, list[dict[str, object]]] = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            self.data = {}

    def _key(self, key: RunKey) -> str:
        return "|".join((self.model, *key))

    def results(self, key: RunKey, runs_per_case: int) -> list[AttemptResult]:
        saved = [AttemptResult.model_validate(r) for r in self.data.get(self._key(key), [])]
        return [r for r in saved if r.attempt < runs_per_case]

    def add(self, key: RunKey, result: AttemptResult) -> None:
        self.data.setdefault(self._key(key), []).append(result.model_dump(mode="json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data), encoding="utf-8")
        os.replace(tmp, self.path)


def confirm_live(
    config: LLMConfig,
    suites: Mapping[str, Suite],
    keys: Sequence[RunKey],
    runs_per_case: int,
    checkpoint: Checkpoint,
) -> bool:
    done = {key: checkpoint.results(key, runs_per_case) for key in keys}
    agent_calls, judge_calls = estimate(suites, keys, runs_per_case, done)
    saved = sum(len(results) for results in done.values())
    by_model = Counter({config.models["agent"]: agent_calls})
    by_model[config.models["judge"]] += judge_calls
    quota = DailyQuota(config.state_dir / "llm-quota.json", SystemClock())

    print(f"Live run: {len(keys)} suite runs x {runs_per_case} runs per case, one call at a time.")
    print(f"  Agent calls: {agent_calls} ({config.models['agent']}), {saved} attempts checkpointed")
    judge_note = "" if judge_calls else " (the manifest's cases use rule judges only)"
    print(f"  Judge calls: {judge_calls} ({config.models['judge']}){judge_note}")
    for model, calls in by_model.items():
        if not calls:
            continue
        used = quota.requests(model)
        left = max(config.rpd - used, 0)
        print(f"  {model}: {calls} calls; daily limit LLM_RPD={config.rpd}, used today {used}")
        if calls > left:
            print(
                f"    More than today's remaining {left}: the run will stop at the quota; "
                "run the script again after it resets to resume."
            )
    minutes = sum(by_model.values()) / config.rpm
    print(f"  At LLM_RPM={config.rpm}: about {minutes:.0f} minutes or more.")
    if agent_calls > config.max_calls_per_run:
        print(
            f"  The demo agents' client stops at LLM_BUDGET_MAX_CALLS_PER_RUN="
            f"{config.max_calls_per_run} per process: run the script again to resume."
        )
    return input("Proceed? [y/N] ").strip().lower() == "y"


# --- running -----------------------------------------------------------------------------


async def run_mock(
    base_url: str, keys: Sequence[RunKey], runs_per_case: int | None, llm: LLMClient | None
) -> dict[RunKey, RunSummary]:
    flaky.reset()  # the support bots' seeded order-lookup flakiness: same draws every time
    options = RunOptions(runs_per_case=runs_per_case)
    return {key: await run_one(base_url, key, options, llm=llm) for key in keys}


def saver(
    checkpoint: Checkpoint,
    key: RunKey,
    stop: asyncio.Event,
    failed: list[tuple[str, AttemptError]],
) -> Callable[[AttemptResult], Awaitable[None]]:
    """Checkpoints each finished attempt; the first error stops the run unsaved, so it's
    retried when the run resumes.
    """

    async def on_result(result: AttemptResult) -> None:
        if result.error is None:
            checkpoint.add(key, result)
        else:
            failed.append((result.case_id, result.error))
            stop.set()

    return on_result


async def run_live(
    base_url: str,
    keys: Sequence[RunKey],
    runs_per_case: int,
    llm: LLMClient | None,
    checkpoint: Checkpoint,
    config: LLMConfig,
) -> dict[RunKey, RunSummary] | None:
    """Every run, resuming from the checkpoint; None if one had to stop early."""
    runs = {}
    options = RunOptions(runs_per_case=runs_per_case, concurrency=1)
    for key in keys:
        print(f"Running {key[0]} against {key[1]} ...", file=sys.stderr)
        stop = asyncio.Event()
        failed: list[tuple[str, AttemptError]] = []
        summary = await run_one(
            base_url,
            key,
            options,
            llm=llm,
            timeout_ms=LIVE_TIMEOUT_MS,
            completed=checkpoint.results(key, runs_per_case),
            on_result=saver(checkpoint, key, stop, failed),
            cancel=stop,
        )
        if failed:
            case_id, error = failed[0]
            print(f"Stopped: {case_id} on {key[1]}: {error.kind} error: {error.message}")
            quota = DailyQuota(config.state_dir / "llm-quota.json", SystemClock())
            for model in {config.models["agent"], config.models["judge"]}:
                if quota.requests(model) >= config.rpd:
                    print(f"  {model} has used its daily quota (LLM_RPD={config.rpd}).")
            print(f"Finished attempts are saved in {checkpoint.path}; run again to resume.")
            return None
        runs[key] = summary
    return runs


# --- the report --------------------------------------------------------------------------


def cell(text: str) -> str:
    """Safe inside a Markdown table cell."""
    text = " ".join(text.split()).replace("|", "\\|")
    return text.replace("<", "&lt;").replace(">", "&gt;")


def agent_routes(flaws: Sequence[Flaw]) -> list[str]:
    return list(dict.fromkeys(flaw.route for flaw in flaws))


def render(
    results: Sequence[FlawResult],
    runs: Mapping[RunKey, RunSummary],
    *,
    heading: str,
    method: str,
) -> str:
    flaws = [r.flaw for r in results]
    routes = agent_routes(flaws)
    detected = sum(r.detected for r in results)
    controls = sum(r.control_passed for r in results)
    lines = [
        f"### {heading}",
        f"**Detected {detected} of {len(results)} planted vulnerabilities across {len(routes)} "
        f"demo agents** ({', '.join(f'`{r}`' for r in routes)}). Negative controls: "
        f"{controls} of {len(results)} passed.",
        "",
        method,
        "",
        "| Flaw | Agent | Case | Result | Detected | How | Negative control |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        flaw = result.flaw
        run = runs[(flaw.suite, flaw.route)]
        outcome = []
        for case in run.cases:
            if case.case_id in flaw.case_ids:
                summary = case.summary
                outcome.append(f"{case.label} ({summary.passes}/{summary.attempts} passed)")
        control = result.control_reason
        if not result.control_passed:
            control = f"**failed**: {control}"
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    flaw.id,
                    flaw.route,
                    ", ".join(flaw.case_ids),
                    "; ".join(outcome) or "missing",
                    "yes" if result.detected else "**no**",
                    result.reason,
                    control,
                )
            )
            + " |"
        )
    missed = [r for r in results if not r.detected]
    lines.append("")
    if missed:
        lines.append("Not detected:")
        lines += [f"- `{r.flaw.id}`: {cell(r.reason)}" for r in missed]
    else:
        lines.append("Not detected: none.")
    failed_controls = [r for r in results if not r.control_passed]
    if failed_controls:
        lines.append("")
        lines.append("Negative controls that failed (the case also fails without the flaw):")
        lines += [f"- `{r.flaw.id}`: {cell(r.control_reason)}" for r in failed_controls]
    return "\n".join(lines)


def write_section(mode: str, body: str) -> None:
    start, end = f"<!-- detection:{mode}:start -->", f"<!-- detection:{mode}:end -->"
    text = METRICS.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"{METRICS} has no {start} ... {end} markers")
    updated = pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)
    METRICS.write_text(updated, encoding="utf-8", newline="\n")


# --- main --------------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> int:
    flaws = load_manifest()
    keys = required_runs(flaws)
    suites = {path: load_suite(path) for path, _ in keys}
    needs_llm = any(uses_llm(suite) for suite in suites.values())
    today = datetime.now(UTC).date().isoformat()

    if not args.live:
        llm = await create_client(verify=False) if needs_llm else None
        with serve_in_background() as base_url:
            runs = await run_mock(base_url, keys, args.runs_per_case, llm)
        per_case = args.runs_per_case or "each suite's own `runs_per_case`"
        method = (
            f"Mock mode, measured {today} by `scripts/measure_detection.py`: the demo agents' "
            "deterministic rule engine (`AGENT_MODE=mock`) and the mock LLM, runs per case: "
            f"{per_case}. This proves the whole pipeline (suite, HTTP adapter, judges, "
            "statistics) catches each flaw end to end and passes the same cases on an agent "
            "without it. It says nothing about live models: the planted flaws here are "
            "deterministic rules."
        )
        heading = "Mock mode"
    else:
        config = LLMConfig.from_env()
        runs_per_case = args.runs_per_case or LIVE_RUNS_PER_CASE
        models = f"{config.models['agent']},{config.models['judge']}"
        checkpoint = Checkpoint(config.state_dir / "detection-live.json", models)
        if not confirm_live(config, suites, keys, runs_per_case, checkpoint):
            print("Not started.")
            return 1
        llm = await create_client(config, verify=False) if needs_llm else None
        with serve_in_background() as base_url:
            live_runs = await run_live(base_url, keys, runs_per_case, llm, checkpoint, config)
        if live_runs is None:
            return 4
        runs = live_runs
        method = (
            f"Live mode, finished {today} by `scripts/measure_detection.py --live`: the demo "
            f"agents answer with `{config.models['agent']}` (`AGENT_MODE=llm`), LLM judges use "
            f"`{config.models['judge']}`, {runs_per_case} runs per case. In llm mode the demo "
            "agents are a system prompt and a model: they report no tool calls, and the RAG "
            "bot doesn't read request `context` (see the reasons below)."
        )
        heading = "Live mode"

    results = evaluate(flaws, runs)
    body = render(results, runs, heading=heading, method=method)
    write_section("live" if args.live else "mock", body)
    print(body)
    print(f"\nWritten to {METRICS}.", file=sys.stderr)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true", help="live model (needs RUN_LIVE=1)")
    parser.add_argument(
        "--runs-per-case",
        type=int,
        help=f"default: each suite's own in mock mode, {LIVE_RUNS_PER_CASE} in live mode",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.live and os.environ.get("RUN_LIVE") != "1":
        sys.exit("--live calls a live LLM: set RUN_LIVE=1 (and the provider key) first")
    # Read per request by the demo agents and per client by the LLM layer: set before either.
    os.environ["AGENT_MODE"] = "llm" if arguments.live else "mock"
    os.environ["LLM_PROVIDER"] = "litellm" if arguments.live else "mock"
    sys.exit(asyncio.run(main(arguments)))
