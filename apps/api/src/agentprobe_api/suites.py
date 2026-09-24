"""Suites: upload/update YAML, validate without saving, sync immutable `test_cases` rows
per version (PLAN.md §2 #1, §2 #9-13).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CurrentPrincipal, Db, Principal
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Project, Suite, TestCase
from agentprobe_api.projects import owned_project
from agentprobe_core.suite import Case, SuiteParseError, parse_suite_yaml
from agentprobe_core.suite import Suite as SuiteSchema

router = APIRouter(tags=["suites"])


async def owned_suite(db: AsyncSession, principal: Principal, suite_id: uuid.UUID) -> Suite:
    """Not-owned and nonexistent are both 404 (mirrors `owned_project`)."""
    suite = await db.scalar(
        select(Suite)
        .join(Project, Project.id == Suite.project_id)
        .where(Suite.id == suite_id, Project.user_id == principal.user_id)
    )
    if suite is None or (
        principal.project_id is not None and suite.project_id != principal.project_id
    ):
        raise ApiError(404, "Suite not found")
    return suite


def _case_row(suite_id: uuid.UUID, suite_version: int, case: Case) -> TestCase:
    return TestCase(
        suite_id=suite_id,
        suite_version=suite_version,
        case_key=case.id,
        input=case.input,
        attack_type=case.attack,
        expectations={"judges": [j.model_dump(mode="json", by_alias=True) for j in case.expect]},
        context={"documents": case.context} if case.context else None,
        call=None,  # MCP `call` cases land with the MCP adapter (SPEC.md §4.2)
    )


def _parse_or_422(yaml_text: str) -> SuiteSchema:
    try:
        return parse_suite_yaml(yaml_text)
    except SuiteParseError as exc:
        raise ApiError(422, "Suite validation failed", details=exc.issues) from exc


# --- request/response models --------------------------------------------------------


class SuiteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    yaml: str = Field(min_length=1)


class SuiteOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    case_count: int
    created_at: datetime


class SuiteValidateOut(BaseModel):
    valid: bool
    case_count: int | None = None
    issues: list[str] = Field(default_factory=list)


# --- routes ----------------------------------------------------------------------------


@router.post("/projects/{project_id}/suites", status_code=201)
async def create_suite(
    project_id: uuid.UUID, body: SuiteIn, principal: CurrentPrincipal, db: Db
) -> SuiteOut:
    project = await owned_project(db, principal, project_id)
    parsed = _parse_or_422(body.yaml)
    suite = Suite(project_id=project.id, name=parsed.suite, yaml_source=body.yaml, version=1)
    db.add(suite)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "A suite with this name already exists in this project") from exc
    for case in parsed.cases:
        db.add(_case_row(suite.id, suite.version, case))
    await db.flush()
    return SuiteOut(
        id=suite.id,
        name=suite.name,
        version=suite.version,
        case_count=len(parsed.cases),
        created_at=suite.created_at,
    )


@router.get("/projects/{project_id}/suites")
async def list_suites(project_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> list[SuiteOut]:
    project = await owned_project(db, principal, project_id)
    rows = await db.execute(
        select(Suite, func.count(TestCase.id))
        .outerjoin(
            TestCase,
            (TestCase.suite_id == Suite.id) & (TestCase.suite_version == Suite.version),
        )
        .where(Suite.project_id == project.id)
        .group_by(Suite.id)
        .order_by(Suite.name)
    )
    return [
        SuiteOut(
            id=suite.id,
            name=suite.name,
            version=suite.version,
            case_count=count,
            created_at=suite.created_at,
        )
        for suite, count in rows
    ]


@router.put("/suites/{suite_id}")
async def update_suite(
    suite_id: uuid.UUID, body: SuiteIn, principal: CurrentPrincipal, db: Db
) -> SuiteOut:
    suite = await owned_suite(db, principal, suite_id)
    parsed = _parse_or_422(body.yaml)
    if body.yaml == suite.yaml_source:  # no-op: nothing changed, no new version
        current_count = await db.scalar(
            select(func.count(TestCase.id)).where(
                TestCase.suite_id == suite.id, TestCase.suite_version == suite.version
            )
        )
        return SuiteOut(
            id=suite.id,
            name=suite.name,
            version=suite.version,
            case_count=current_count or 0,
            created_at=suite.created_at,
        )
    suite.name = parsed.suite
    suite.version += 1
    suite.yaml_source = body.yaml
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "A suite with this name already exists in this project") from exc
    for case in parsed.cases:
        db.add(_case_row(suite.id, suite.version, case))
    await db.flush()
    return SuiteOut(
        id=suite.id,
        name=suite.name,
        version=suite.version,
        case_count=len(parsed.cases),
        created_at=suite.created_at,
    )


@router.post("/suites/validate")
async def validate_suite(body: SuiteIn, principal: CurrentPrincipal) -> SuiteValidateOut:
    try:
        parsed = parse_suite_yaml(body.yaml)
    except SuiteParseError as exc:
        return SuiteValidateOut(valid=False, issues=exc.issues)
    return SuiteValidateOut(valid=True, case_count=len(parsed.cases))
