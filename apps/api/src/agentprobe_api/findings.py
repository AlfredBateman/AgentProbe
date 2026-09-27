"""Failure clustering (SPEC.md §4.8, PLAN.md C4, ADR 0024): after a run finishes, its
failing outputs are embedded and grouped into findings -- "N failures -> K root causes" --
each with an LLM-written label, summary and suggested fix. The clustering itself
(`agentprobe_core.findings`) is pure and DB-free; this module is the persistence around it
and the read endpoint.

Clustering never fails the run it follows: `cluster_run` is called after a queued or inline
run completes (`queue.cluster_findings`, ADR 0017) and from `/ci/report`'s own transaction
(ADR 0018); both catch and log instead of letting a clustering bug fail the run.
"""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CurrentPrincipal, Db
from agentprobe_api.models import Finding, RunResult, TestCase
from agentprobe_api.runs import owned_run
from agentprobe_core.findings import FailingOutput, cluster_failures
from agentprobe_core.llm.types import LLMClient

router = APIRouter(tags=["findings"])


class FindingOut(BaseModel):
    id: uuid.UUID
    cluster_label: str
    summary: str
    suggested_fix: str | None
    member_result_ids: list[uuid.UUID]


def _out(row: Finding) -> FindingOut:
    return FindingOut(
        id=row.id,
        cluster_label=row.cluster_label,
        summary=row.summary,
        suggested_fix=row.suggested_fix,
        member_result_ids=list(row.member_result_ids),
    )


@router.get("/runs/{run_id}/findings")
async def list_findings(run_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> list[FindingOut]:
    """Largest clusters (most failing attempts) first."""
    await owned_run(db, principal, run_id)
    rows = await db.scalars(select(Finding).where(Finding.run_id == run_id))
    ordered = sorted(rows, key=lambda f: len(f.member_result_ids), reverse=True)
    return [_out(f) for f in ordered]


async def _read_failed_outputs(db: AsyncSession, run_id: uuid.UUID) -> list[FailingOutput]:
    rows = await db.execute(
        select(RunResult.id, RunResult.output)
        .join(TestCase, TestCase.id == RunResult.case_id)
        .where(
            RunResult.run_id == run_id,
            RunResult.status == "failed",
            RunResult.output.is_not(None),
        )
        .order_by(TestCase.case_key, RunResult.attempt)
    )
    return [(str(result_id), output) for result_id, output in rows.tuples() if output is not None]


async def cluster_run(db: AsyncSession, run_id: uuid.UUID, llm: LLMClient) -> list[Finding]:
    """Embeds and clusters `run_id`'s failing outputs and (re)writes its findings, in the
    caller's own transaction. Idempotent: replaces whatever findings this run already has,
    so a re-run (a retried job, `/ci/report` re-ingesting) doesn't duplicate them.
    """
    items = await _read_failed_outputs(db, run_id)
    drafts = await cluster_failures(items, llm)
    await db.execute(delete(Finding).where(Finding.run_id == run_id))
    rows = [
        Finding(
            run_id=run_id,
            cluster_label=d.label,
            summary=d.summary,
            suggested_fix=d.suggested_fix,
            embedding=d.embedding,
            member_result_ids=[uuid.UUID(rid) for rid in d.member_result_ids],
        )
        for d in drafts
    ]
    db.add_all(rows)
    await db.flush()
    return rows
