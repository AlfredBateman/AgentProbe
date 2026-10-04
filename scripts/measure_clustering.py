"""How much does failure clustering actually collapse a run's failures? (docs/metrics.md)

    uv run python scripts/measure_clustering.py

Runs the smoke suite against the bundled vulnerable demo agent (mock mode, offline) through
core's `run_suite`, then clusters its failing results with `agentprobe_core.findings`
exactly as `apps/api/findings.py` does for a live run. Writes "N failures -> K root causes"
and a per-finding table into docs/metrics.md.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from agentprobe_core.findings import ClusterFinding, cluster_failures
from agentprobe_core.llm import create_client
from agentprobe_demo_agents import flaky
from agentprobe_demo_agents.detection import run_one
from agentprobe_demo_agents.main import serve_in_background

REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS = REPO_ROOT / "docs" / "metrics.md"
SMOKE_SUITE = "suites/examples/smoke.yaml"
ROUTE = "/vulnerable"


def cell(text: str) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text.replace("<", "&lt;").replace(">", "&gt;")


def render(failing: int, findings: list[ClusterFinding]) -> str:
    lines = [
        "### Mock mode",
        f"**{failing} failing results collapse into {len(findings)} findings** on the "
        f"vulnerable demo bot ({SMOKE_SUITE} against `{ROUTE}`).",
        "",
        "Mock mode, offline: the demo agent's deterministic rule engine and the mock "
        "embedding/summarizer (`agentprobe_core.llm.mock`). Each planted flaw's repeated "
        "attempts give (near-)identical output, so they collapse into one finding; the "
        "flaws themselves stay in separate findings.",
        "",
        "| Finding | Members | Label |",
        "|---|---|---|",
    ]
    for finding in sorted(findings, key=lambda f: len(f.member_result_ids), reverse=True):
        members = len(finding.member_result_ids)
        lines.append(f"| {cell(finding.summary)} | {members} | {cell(finding.label)} |")
    return "\n".join(lines)


def write_section(body: str) -> None:
    start, end = "<!-- clustering:mock:start -->", "<!-- clustering:mock:end -->"
    text = METRICS.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(start) + ".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"{METRICS} has no {start} ... {end} markers")
    updated = pattern.sub(lambda _: f"{start}\n{body}\n{end}", text)
    METRICS.write_text(updated, encoding="utf-8", newline="\n")


async def main() -> int:
    flaky.reset()
    llm = await create_client(verify=False)
    with serve_in_background() as base_url:
        summary = await run_one(base_url, (SMOKE_SUITE, ROUTE), llm=llm)
    items = [
        (f"{r.case_id}#{r.attempt}", r.response.output)
        for r in summary.results
        if r.status == "failed" and r.response is not None
    ]
    findings = await cluster_failures(items, llm)
    body = render(len(items), findings)
    write_section(body)
    print(body)
    print(f"\nWritten to {METRICS}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    os.environ["AGENT_MODE"] = "mock"
    os.environ["LLM_PROVIDER"] = "mock"
    sys.exit(asyncio.run(main()))
