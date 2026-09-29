"""Caps for a public deploy (ADR 0035): signups, per-user resources, runs per day, and the
worst case of live LLM spend. Each setting is None by default (unlimited).

ponytail: count-then-insert, so two concurrent requests can overshoot a cap by one each. A
unique constraint can't express a count; add row locks if an exact cap ever matters.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Project, Run, Suite, User
from agentprobe_api.settings import Settings
from agentprobe_core.llm import LLMConfig, LLMConfigError

DAY = timedelta(days=1)


def _since() -> datetime:
    return datetime.now(UTC) - DAY


async def check_signups(db: AsyncSession, settings: Settings) -> None:
    cap = settings.max_signups_per_day
    if cap is None:
        return
    count = await db.scalar(select(func.count(User.id)).where(User.created_at >= _since()))
    if (count or 0) >= cap:
        raise ApiError(429, "Registration is paused: today's signup limit is reached")


async def check_projects(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None:
    cap = settings.max_projects_per_user
    if cap is None:
        return
    count = await db.scalar(select(func.count(Project.id)).where(Project.user_id == user_id))
    if (count or 0) >= cap:
        raise ApiError(403, f"Project limit reached ({cap} per account)")


async def check_agents(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None:
    cap = settings.max_agents_per_user
    if cap is None:
        return
    count = await db.scalar(
        select(func.count(Agent.id))
        .join(Project, Project.id == Agent.project_id)
        .where(Project.user_id == user_id)
    )
    if (count or 0) >= cap:
        raise ApiError(403, f"Agent limit reached ({cap} per account)")


def check_cases(settings: Settings, case_count: int) -> None:
    cap = settings.max_cases_per_suite
    if cap is not None and case_count > cap:
        raise ApiError(422, f"A suite may have at most {cap} cases on this server")


async def check_runs(db: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None:
    cap = settings.max_runs_per_user_per_day
    if cap is None:
        return
    count = await db.scalar(
        select(func.count(Run.id))
        .join(Suite, Suite.id == Run.suite_id)
        .join(Project, Project.id == Suite.project_id)
        .where(Project.user_id == user_id, Run.created_at >= _since())
    )
    if (count or 0) >= cap:
        raise ApiError(429, f"Daily run limit reached ({cap} per account per 24 hours)")


async def check_live_budget(db: AsyncSession, settings: Settings, *, mock: bool) -> None:
    """Refuses a live-LLM run when every live run of the last 24 hours, at its worst case,
    plus this one would exceed LLM_GLOBAL_USD_PER_DAY.

    A live run builds at most two budget-guarded clients (judges, then clustering), each
    capped at LLM_BUDGET_USD_PER_RUN, so it can't spend more than twice that. Counting the
    worst case, not the metered cost, keeps the bound exact without trusting spend that
    `/ci/report` payloads claim. A run resumed after a crash builds fresh clients, so it can
    exceed its reservation (ADR 0035).
    """
    cap = settings.llm_global_usd_per_day
    if mock or cap is None:
        return
    try:
        config = LLMConfig.from_env()
    except LLMConfigError:
        return  # the run fails on this same config before any LLM call: nothing is spent
    if config.provider == "mock":
        return  # nothing live will be called
    reserve = 2 * config.max_usd_per_run
    live_runs = await db.scalar(
        select(func.count(Run.id)).where(Run.mock_mode.is_(False), Run.created_at >= _since())
    )
    if ((live_runs or 0) + 1) * reserve > cap:
        raise ApiError(429, "The server's daily live-LLM budget is spent; run with mock judges")
