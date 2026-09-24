import uuid
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.crypto import SecretBox
from agentprobe_api.models import (
    Agent,
    Base,
    Baseline,
    Finding,
    Judgment,
    Project,
    Run,
    RunCaseSummary,
    RunResult,
    Secret,
    Suite,
    TestCase,
    Trace,
    User,
)
from agentprobe_api.settings import get_settings

pytestmark = pytest.mark.integration


async def add[T: Base](db: AsyncSession, obj: T) -> T:
    db.add(obj)
    await db.flush()
    return obj


async def make_run(db: AsyncSession) -> tuple[Run, TestCase, RunResult]:
    user = await add(db, User(email=f"{uuid.uuid4()}@example.com", password_hash="fake"))
    project = await add(db, Project(user_id=user.id, name="p"))
    suite = await add(
        db, Suite(project_id=project.id, name="s", yaml_source="cases: []", version=1)
    )
    agent = await add(db, Agent(project_id=project.id, name="a", adapter_type="http", config={}))
    case = await add(
        db,
        TestCase(suite_id=suite.id, suite_version=1, case_key="c1", input="hi", expectations={}),
    )
    run = await add(
        db,
        Run(
            suite_id=suite.id,
            suite_version=1,
            agent_id=agent.id,
            status="completed",
            runs_per_case=1,
            mock_mode=True,
            config_snapshot={"suite": "cases: []", "agent": {}},
            attempts_total=1,
        ),
    )
    result = await add(
        db, RunResult(run_id=run.id, case_id=case.id, attempt=1, status="passed", detail={})
    )
    return run, case, result


async def test_full_graph_round_trips(db: AsyncSession) -> None:
    run, case, result = await make_run(db)
    box = SecretBox(Fernet.generate_key().decode())
    agent = await db.get_one(Agent, run.agent_id)
    secret = await add(
        db, Secret(project_id=agent.project_id, ciphertext=box.encrypt("Bearer fake"))
    )
    agent.secret_ref = secret.id
    embedding = [0.5] * get_settings().embedding_dim
    for obj in [
        Trace(run_result_id=result.id, steps=[{"role": "user", "content": "hi"}]),
        Judgment(run_result_id=result.id, judge_type="contains", status="pass", passed=True),
        Judgment(
            run_id=run.id,
            case_id=case.id,
            judge_type="consistency",
            status="pass",
            passed=True,
            score=1,
        ),
        RunCaseSummary(
            run_id=run.id,
            case_id=case.id,
            attempts=1,
            passes=1,
            pass_rate=1.0,
            label="stable-pass",
            total_cost=Decimal("0.000125"),
        ),
        Finding(
            run_id=run.id,
            cluster_label="k",
            summary="s",
            embedding=embedding,
            member_result_ids=[result.id],
        ),
        Baseline(project_id=agent.project_id, branch="main", run_id=run.id),
    ]:
        await add(db, obj)
    db.expunge_all()

    stored = await db.get_one(Secret, secret.id)
    assert box.decrypt(stored.ciphertext).get_secret_value() == "Bearer fake"
    assert (await db.get_one(Agent, agent.id)).secret_ref == secret.id
    finding = (await db.execute(select(Finding).where(Finding.run_id == run.id))).scalar_one()
    assert finding.embedding == embedding
    assert finding.member_result_ids == [result.id]
    summary = await db.get_one(RunCaseSummary, (run.id, case.id))
    assert summary.total_cost == Decimal("0.000125")


async def test_run_result_attempt_is_unique(db: AsyncSession) -> None:
    run, case, _ = await make_run(db)
    with pytest.raises(IntegrityError, match="uq_run_results_run_id_case_id_attempt"):
        async with db.begin_nested():
            await add(
                db,
                RunResult(run_id=run.id, case_id=case.id, attempt=1, status="failed", detail={}),
            )


@pytest.mark.parametrize("scope", ["both", "neither"])
async def test_judgment_needs_exactly_one_scope(db: AsyncSession, scope: str) -> None:
    run, case, result = await make_run(db)
    ids = (
        {"run_result_id": result.id, "run_id": run.id, "case_id": case.id}
        if scope == "both"
        else {}
    )
    with pytest.raises(IntegrityError, match="ck_judgments_one_scope"):
        async with db.begin_nested():
            await add(db, Judgment(judge_type="x", status="fail", passed=False, **ids))


async def test_judgment_status_and_error_kind_are_checked(db: AsyncSession) -> None:
    run, case, result = await make_run(db)
    with pytest.raises(IntegrityError, match="ck_judgments_status"):
        async with db.begin_nested():
            await add(
                db,
                Judgment(run_result_id=result.id, judge_type="x", status="maybe", passed=False),
            )
    with pytest.raises(IntegrityError, match="ck_run_results_error_kind"):
        async with db.begin_nested():
            await add(
                db,
                RunResult(
                    run_id=run.id,
                    case_id=case.id,
                    attempt=2,
                    status="error",
                    error_kind="gremlins",
                    detail={},
                ),
            )


async def test_share_token_hash_is_unique(db: AsyncSession) -> None:
    run, _, _ = await make_run(db)
    other, _, _ = await make_run(db)
    run.share_token_hash = "a" * 64
    await db.flush()
    with pytest.raises(IntegrityError, match="uq_runs_share_token_hash"):
        async with db.begin_nested():
            other.share_token_hash = "a" * 64
            await db.flush()


async def test_summary_label_is_checked(db: AsyncSession) -> None:
    run, case, _ = await make_run(db)
    with pytest.raises(IntegrityError, match="ck_run_case_summaries_label"):
        async with db.begin_nested():
            await add(
                db,
                RunCaseSummary(
                    run_id=run.id, case_id=case.id, attempts=1, passes=1, pass_rate=1, label="ok"
                ),
            )


# The two tests below each insert the same row; either fails if the other leaked.
ISOLATION_EMAIL = "isolation-probe@example.com"


@pytest.mark.parametrize("attempt", [1, 2])
async def test_tests_are_isolated(db: AsyncSession, attempt: int) -> None:
    count = select(func.count()).select_from(User).where(User.email == ISOLATION_EMAIL)
    assert (await db.execute(count)).scalar_one() == 0
    db.add(User(email=ISOLATION_EMAIL, password_hash="fake"))
    await db.commit()  # commits hit a savepoint; the outer transaction still rolls back
    assert (await db.execute(count)).scalar_one() == 1
