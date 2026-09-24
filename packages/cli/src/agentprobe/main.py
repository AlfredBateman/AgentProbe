"""The `agentprobe` CLI: run suites locally, keep baselines, compare runs.

Every run goes through `agentprobe_core.runner.run_suite`, the single run implementation
shared with the server (PLAN.md B1.7, ADR 0016); nothing here reimplements run logic.
"""

import asyncio
import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from enum import IntEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import TypeAdapter, ValidationError
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.text import Text
from typer._click.exceptions import UsageError  # typer vendors click; not re-exported
from typer.core import TyperGroup

from agentprobe import report
from agentprobe.config import CONFIG_FILE, ConfigError, build_adapter, load_config
from agentprobe_core.adapters.types import AgentAdapter
from agentprobe_core.llm import LLMConfig, LLMConfigError, create_client
from agentprobe_core.runner import (
    INFRA_ERRORS,
    AttemptResult,
    RunOptions,
    RunSummary,
    run_suite,
    uses_llm,
)
from agentprobe_core.stats import RegressionReport, compare_runs
from agentprobe_core.suite import StatisticsConfig, Suite, SuiteParseError, parse_suite_yaml


class ExitCode(IntEnum):
    OK = 0
    THRESHOLD = 1  # pass rate below --fail-under
    REGRESSION = 2  # statistically significant regression against the baseline
    USAGE = 3  # bad arguments, config or suite
    INFRA = 4  # the run itself broke: agent unreachable, LLM budget used up, ...


EXIT_CODES = """Exit codes:
  0  passed
  1  pass rate below --fail-under (default 1.0: every case must pass)
  2  regression against the baseline (statistically significant)
  3  usage, config or suite error
  4  infrastructure error (agent unreachable, LLM budget used up, internal error)"""

SMALL_N = (
    "Statistics: an attempt passes when every judge passes; the pass rate is the mean of "
    "per-case pass rates, with a 95% case-level bootstrap CI. A regression needs a "
    "significant drop (one-sided Fisher exact per case with Tarone-Holm, paired sign-flip "
    "for the suite) of at least --min-drop. Small-N limit: at 5 runs per case a single case "
    "is flagged only on a large drop (5/5 -> 1/5 or worse); at 3 runs even 3/3 -> 0/3 is "
    "borderline (p = 0.05). Use 5 or more runs per case to gate on regressions."
)

_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}")


@contextmanager
def _usage_exit() -> Iterator[None]:
    try:
        yield
    except UsageError as exc:  # click exits 2 on usage errors: that's our regression code
        exc.exit_code = ExitCode.USAGE
        raise


class _Group(TyperGroup):
    def make_context(self, *args: Any, **kwargs: Any) -> Any:
        with _usage_exit():
            return super().make_context(*args, **kwargs)

    def invoke(self, ctx: Any) -> Any:
        with _usage_exit():
            return super().invoke(ctx)


app = typer.Typer(
    cls=_Group,
    help="AgentProbe: test AI agents for flakiness, regressions and security flaws.",
    epilog=EXIT_CODES,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)
baseline_app = typer.Typer(cls=_Group, help="Local baselines (.agentprobe/baselines/).")
app.add_typer(baseline_app, name="baseline")


def _state_dir() -> Path:
    return Path(os.environ.get("AGENTPROBE_STATE_DIR", ".agentprobe"))


def _fail(console: Console, message: str, code: ExitCode = ExitCode.USAGE) -> typer.Exit:
    console.print(Text("error: ", style="red").append(report.safe(message, newlines=True)))
    return typer.Exit(code)


def _load_run(ref: str) -> RunSummary:
    """A run file path, or the name of a saved baseline."""
    path = Path(ref)
    if not path.is_file() and _NAME.fullmatch(ref):
        path = _state_dir() / "baselines" / f"{ref}.json"
    if not path.is_file():
        raise ConfigError(f"{ref}: no such run file or baseline name")
    try:
        return RunSummary.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise ConfigError(
            f"{path}: not an AgentProbe run file ({exc.error_count()} errors)"
        ) from None


def _statistics(base: StatisticsConfig, **flags: float | None) -> StatisticsConfig:
    try:
        return base.override(**flags)
    except ValidationError as exc:
        raise ConfigError(f"invalid statistics flag: {exc.errors()[0]['msg']}") from None


def _compare(baseline: RunSummary, candidate: RunSummary, config: StatisticsConfig) -> Any:
    if baseline.suite != candidate.suite:
        raise ConfigError(
            f"the baseline is a run of suite {baseline.suite!r}, not {candidate.suite!r}"
        )
    return compare_runs(baseline.case_summaries(), candidate.case_summaries(), config)


def _save(summary: RunSummary) -> Path:
    runs = _state_dir() / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    stamp = summary.started_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    suite = re.sub(r"[^A-Za-z0-9_.-]", "_", summary.suite)[:50]  # never a path component
    path = runs / f"{stamp}-{suite}-{summary.id[:8]}.json"
    path.write_text(summary.model_dump_json(indent=2), "utf-8")
    return path


def _exit_code(
    summary: RunSummary, fail_under: float, regression: RegressionReport | None
) -> ExitCode:
    if summary.infra_errors:
        return ExitCode.INFRA
    if regression is not None and regression.verdict == "regression":
        return ExitCode.REGRESSION
    if summary.pass_rate is None or summary.pass_rate + 1e-9 < fail_under:
        return ExitCode.THRESHOLD
    return ExitCode.OK


async def _execute(
    suite: Suite,
    adapter: AgentAdapter,
    llm_config: LLMConfig | None,
    options: RunOptions,
    *,
    agent: str,
    progress: Progress,
) -> RunSummary:
    total = len(suite.cases) * (options.runs_per_case or suite.runs_per_case)
    task = progress.add_task(f"{suite.suite} -> {agent}", total=total, status="")
    counts: Counter[str] = Counter()
    # Fail fast: once one attempt hits an infrastructure error (agent down, budget used up),
    # the rest would burn their retries on the same failure and the exit code is 4 anyway.
    stop = asyncio.Event()

    async def on_result(result: AttemptResult) -> None:
        counts[result.status] += 1
        status = ", ".join(f"{counts[s]} {s}" for s in ("passed", "failed", "error") if counts[s])
        progress.update(task, advance=1, status=status)
        if result.error is not None and result.error.kind in INFRA_ERRORS:
            stop.set()

    try:
        try:
            llm = await create_client(llm_config) if llm_config else None
        except LLMConfigError as exc:
            raise ConfigError(f"LLM provider: {exc}") from None
        return await run_suite(
            suite, adapter, llm=llm, options=options, agent=agent, on_result=on_result, cancel=stop
        )
    finally:
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()


@app.command()
def init(
    force: Annotated[bool, typer.Option(help="Overwrite existing files.")] = False,
) -> None:
    """Scaffold agentprobe.yaml (agents, LLM provider) and an example suite."""
    console = Console(stderr=True)
    files = {Path(CONFIG_FILE): report.INIT_CONFIG, Path("suites/example.yaml"): report.INIT_SUITE}
    existing = [str(path) for path in files if path.exists()]
    if existing and not force:
        raise _fail(console, f"{', '.join(existing)} already exist; use --force to overwrite")
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, "utf-8")
        console.print(f"created {path}")
    console.print(
        "next: start your agent, edit agentprobe.yaml, then `agentprobe run suites/example.yaml`"
    )


@app.command(epilog=f"{SMALL_N}\n\n{EXIT_CODES}")
def run(
    suite_file: Annotated[Path, typer.Argument(help="Suite YAML file.", show_default=False)],
    agent: Annotated[
        str | None,
        typer.Option(help="Agent name from agentprobe.yaml. Default: the suite's `agent`."),
    ] = None,
    config: Annotated[Path, typer.Option(help="Project config file.")] = Path(CONFIG_FILE),
    mock: Annotated[
        bool, typer.Option("--mock", help="Force the mock LLM provider for judges (no live calls).")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print the full result as JSON on stdout.")
    ] = False,
    runs_per_case: Annotated[
        int | None, typer.Option(min=1, max=20, help="Override the suite's runs_per_case.")
    ] = None,
    fail_under: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Minimum pass rate (point estimate).")
    ] = 1.0,
    baseline: Annotated[
        str | None,
        typer.Option(help="Baseline run file, or a name saved with `agentprobe baseline set`."),
    ] = None,
    concurrency: Annotated[
        int | None, typer.Option(min=1, max=64, help="Attempts in flight at once.")
    ] = None,
    alpha: Annotated[float | None, typer.Option(help="Significance level (default 0.05).")] = None,
    min_drop: Annotated[
        float | None, typer.Option(help="Smallest pass-rate drop that counts (default 0.05).")
    ] = None,
    permutation_draws: Annotated[int | None, typer.Option(help="Suite-test draws.")] = None,
    bootstrap_resamples: Annotated[int | None, typer.Option(help="CI resamples.")] = None,
) -> None:
    """Run a suite against an agent locally and save the result to .agentprobe/runs/."""
    err = Console(stderr=True)
    try:
        try:
            suite = parse_suite_yaml(suite_file.read_text("utf-8"))
        except OSError as exc:
            raise ConfigError(f"can't read {suite_file}: {exc.strerror}") from None
        except SuiteParseError as exc:
            raise ConfigError(f"{suite_file}:\n  " + "\n  ".join(exc.issues)) from None
        statistics = _statistics(
            suite.statistics,
            alpha=alpha,
            min_drop=min_drop,
            permutation_draws=permutation_draws,
            bootstrap_resamples=bootstrap_resamples,
        )
        base = _load_run(baseline) if baseline else None
        if base is not None and base.suite != suite.suite:
            raise ConfigError(f"the baseline is a run of suite {base.suite!r}, not {suite.suite!r}")
        project = load_config(config)
        agent = agent or suite.agent
        agent_config = project.agents.get(agent)
        if agent_config is None:
            have = ", ".join(sorted(project.agents)) or "none"
            raise ConfigError(f"agent {agent!r} is not in {config} (agents: {have})")
        llm_config = None
        if uses_llm(suite):
            env = dict(os.environ)
            env.setdefault("LLM_PROVIDER", project.llm.provider)
            if mock:
                env["LLM_PROVIDER"] = "mock"
            try:
                llm_config = LLMConfig.from_env(env)
            except LLMConfigError as exc:
                raise ConfigError(f"LLM provider: {exc}") from None
        options = RunOptions(
            runs_per_case=runs_per_case,
            concurrency=concurrency or project.run.concurrency,
            max_retries=project.run.retries,
            statistics=statistics,
            agent_price=agent_config.price,
        )
        adapter = build_adapter(agent_config, config.resolve().parent)
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("{task.fields[status]}"),
            console=err,
            transient=True,
        ) as progress:
            summary = asyncio.run(
                _execute(suite, adapter, llm_config, options, agent=agent, progress=progress)
            )
        regression = _compare(base, summary, statistics) if base else None
    except (ConfigError, ValueError) as exc:
        raise _fail(err, str(exc)) from None

    path = _save(summary)
    code = _exit_code(summary, fail_under, regression)
    if json_output:
        payload = {
            "file": str(path),
            "exit_code": int(code),
            "run": summary.model_dump(mode="json"),
            "regression": TypeAdapter(RegressionReport).dump_python(regression, mode="json")
            if regression
            else None,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        out = Console()
        report.render_run(out, summary, fail_under=fail_under, regression=regression)
        report.render_verdict(out, code.name, int(code), path)
    raise typer.Exit(code)


@app.command(epilog=f"{SMALL_N}\n\nExits 2 on a regression, 3 on a usage error, else 0.")
def compare(
    baseline: Annotated[str, typer.Argument(help="Baseline run file or baseline name.")],
    candidate: Annotated[str, typer.Argument(help="Candidate run file or baseline name.")],
    alpha: Annotated[float | None, typer.Option(help="Significance level.")] = None,
    min_drop: Annotated[float | None, typer.Option(help="Smallest drop that counts.")] = None,
    permutation_draws: Annotated[int | None, typer.Option(help="Suite-test draws.")] = None,
) -> None:
    """Regression diff between two runs of the same suite."""
    err = Console(stderr=True)
    try:
        base, cand = _load_run(baseline), _load_run(candidate)
        config = _statistics(
            cand.statistics, alpha=alpha, min_drop=min_drop, permutation_draws=permutation_draws
        )
        regression = _compare(base, cand, config)
    except ConfigError as exc:
        raise _fail(err, str(exc)) from None
    report.render_comparison(Console(), base, cand, regression)
    raise typer.Exit(ExitCode.REGRESSION if regression.verdict == "regression" else ExitCode.OK)


@baseline_app.command("set")
def baseline_set(
    run_file: Annotated[Path, typer.Argument(help="A run file from .agentprobe/runs/.")],
    name: Annotated[str, typer.Option(help="Baseline name, used as --baseline NAME.")] = "main",
) -> None:
    """Save a run as a named baseline."""
    err = Console(stderr=True)
    if not _NAME.fullmatch(name):
        raise _fail(err, "a baseline name is 1-64 characters of letters, digits, '_', '.', '-'")
    try:
        if not run_file.is_file():
            raise ConfigError(f"{run_file}: no such run file")
        summary = _load_run(str(run_file))
    except ConfigError as exc:
        raise _fail(err, str(exc)) from None
    target = _state_dir() / "baselines" / f"{name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_file, target)
    err.print(
        report.safe(f"baseline {name!r} = {summary.suite} run {summary.id[:8]} ({target})"),
        soft_wrap=True,
    )


def main() -> None:
    app()
