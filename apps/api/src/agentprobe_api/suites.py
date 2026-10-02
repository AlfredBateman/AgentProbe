"""Suites: upload/update YAML, validate without saving, sync immutable `test_cases` rows
per version (PLAN.md §2 #1, §2 #9-13).
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api import limits
from agentprobe_api.auth import AppSettings, CurrentPrincipal, Db, Principal
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Project, Run, Suite, SuiteVersion, TestCase
from agentprobe_api.projects import owned_project
from agentprobe_core.suite import Case, SuiteIssue, SuiteParseError, parse_suite_yaml
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
        call=case.call.model_dump(mode="json") if case.call else None,
    )


def _issue_details(issues: list[SuiteIssue]) -> list[dict[str, object]]:
    """`ApiError.details` goes straight into a plain `JSONResponse`, so it needs plain dicts,
    not pydantic model instances (unlike a `SuiteValidateOut.issues` response field, which
    FastAPI encodes itself).
    """
    return [issue.model_dump(mode="json") for issue in issues]


def _parse_or_422(yaml_text: str) -> SuiteSchema:
    try:
        return parse_suite_yaml(yaml_text)
    except SuiteParseError as exc:
        raise ApiError(422, "Suite validation failed", details=_issue_details(exc.issues)) from exc


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


class SuiteDetailOut(SuiteOut):
    yaml: str


class SuiteValidateOut(BaseModel):
    valid: bool
    case_count: int | None = None
    issues: list[SuiteIssue] = Field(default_factory=list)


class SuiteVersionOut(BaseModel):
    """One version in a suite's history. `has_yaml` is False for versions saved before
    migration 0005, whose YAML was never kept (ADR 0038); their cases still are. `created_at`
    is None when the save time isn't known (those, and the backfilled current version > 1)."""

    version: int
    created_at: datetime | None
    case_count: int
    run_count: int
    has_yaml: bool


class SuiteVersionDetailOut(BaseModel):
    version: int
    yaml: str | None


class CaseOut(BaseModel):
    """A case as stored for one suite version (the suite page's case browser)."""

    id: str
    input: str | None
    call: dict[str, Any] | None
    attack: str | None
    context_count: int
    judges: list[dict[str, Any]]


# --- routes ----------------------------------------------------------------------------


@router.post("/projects/{project_id}/suites", status_code=201)
async def create_suite(
    project_id: uuid.UUID, body: SuiteIn, principal: CurrentPrincipal, db: Db, settings: AppSettings
) -> SuiteOut:
    project = await owned_project(db, principal, project_id)
    parsed = _parse_or_422(body.yaml)
    limits.check_cases(settings, len(parsed.cases))
    suite = Suite(project_id=project.id, name=parsed.suite, yaml_source=body.yaml, version=1)
    db.add(suite)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "A suite with this name already exists in this project") from exc
    _add_version(db, suite, parsed)
    await db.flush()
    return SuiteOut(
        id=suite.id,
        name=suite.name,
        version=suite.version,
        case_count=len(parsed.cases),
        created_at=suite.created_at,
    )


def _add_version(db: AsyncSession, suite: Suite, parsed: SuiteSchema) -> None:
    """The immutable rows of `suite`'s current version: its YAML and its cases."""
    db.add(SuiteVersion(suite_id=suite.id, version=suite.version, yaml_source=suite.yaml_source))
    for case in parsed.cases:
        db.add(_case_row(suite.id, suite.version, case))


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


@router.get("/suites/{suite_id}")
async def get_suite(suite_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> SuiteDetailOut:
    suite = await owned_suite(db, principal, suite_id)
    count = await db.scalar(
        select(func.count(TestCase.id)).where(
            TestCase.suite_id == suite.id, TestCase.suite_version == suite.version
        )
    )
    return SuiteDetailOut(
        id=suite.id,
        name=suite.name,
        version=suite.version,
        case_count=count or 0,
        created_at=suite.created_at,
        yaml=suite.yaml_source,
    )


@router.put("/suites/{suite_id}")
async def update_suite(
    suite_id: uuid.UUID, body: SuiteIn, principal: CurrentPrincipal, db: Db, settings: AppSettings
) -> SuiteOut:
    suite = await owned_suite(db, principal, suite_id)
    parsed = _parse_or_422(body.yaml)
    limits.check_cases(settings, len(parsed.cases))
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
    _add_version(db, suite, parsed)
    await db.flush()
    return SuiteOut(
        id=suite.id,
        name=suite.name,
        version=suite.version,
        case_count=len(parsed.cases),
        created_at=suite.created_at,
    )


@router.get("/suites/{suite_id}/versions")
async def list_versions(
    suite_id: uuid.UUID, principal: CurrentPrincipal, db: Db
) -> list[SuiteVersionOut]:
    """Every version, newest first, with its case and run counts."""
    suite = await owned_suite(db, principal, suite_id)
    # Comprehensions, not dict(result.tuples()): a Result has .keys(), so dict() misreads it.
    cases = {
        v: n
        for v, n in await db.execute(
            select(TestCase.suite_version, func.count())
            .where(TestCase.suite_id == suite.id)
            .group_by(TestCase.suite_version)
        )
    }
    runs = {
        v: n
        for v, n in await db.execute(
            select(Run.suite_version, func.count())
            .where(Run.suite_id == suite.id)
            .group_by(Run.suite_version)
        )
    }
    saved = {
        v: at
        for v, at in await db.execute(
            select(SuiteVersion.version, SuiteVersion.created_at).where(
                SuiteVersion.suite_id == suite.id
            )
        )
    }
    return [
        SuiteVersionOut(
            version=version,
            created_at=saved.get(version),
            case_count=cases.get(version, 0),
            run_count=runs.get(version, 0),
            has_yaml=version in saved,
        )
        for version in sorted(cases.keys() | saved.keys(), reverse=True)
    ]


@router.get("/suites/{suite_id}/versions/{version}")
async def get_version(
    suite_id: uuid.UUID, version: int, principal: CurrentPrincipal, db: Db
) -> SuiteVersionDetailOut:
    suite = await owned_suite(db, principal, suite_id)
    yaml_source = await db.scalar(
        select(SuiteVersion.yaml_source).where(
            SuiteVersion.suite_id == suite.id, SuiteVersion.version == version
        )
    )
    if yaml_source is None and not _version_exists(suite, version):
        raise ApiError(404, "Suite version not found")
    return SuiteVersionDetailOut(version=version, yaml=yaml_source)


@router.get("/suites/{suite_id}/cases")
async def list_cases(
    suite_id: uuid.UUID, principal: CurrentPrincipal, db: Db, version: int | None = None
) -> list[CaseOut]:
    """One version's cases (default: the current one), in the YAML's order when it was kept."""
    suite = await owned_suite(db, principal, suite_id)
    version = suite.version if version is None else version
    rows = list(
        await db.scalars(
            select(TestCase)
            .where(TestCase.suite_id == suite.id, TestCase.suite_version == version)
            .order_by(TestCase.case_key)
        )
    )
    if not rows and not _version_exists(suite, version):
        raise ApiError(404, "Suite version not found")
    yaml_source = await db.scalar(
        select(SuiteVersion.yaml_source).where(
            SuiteVersion.suite_id == suite.id, SuiteVersion.version == version
        )
    )
    if yaml_source is not None:
        try:
            order = {case.id: i for i, case in enumerate(parse_suite_yaml(yaml_source).cases)}
            rows.sort(key=lambda row: order.get(row.case_key, len(order)))
        except SuiteParseError:
            pass  # stored YAML that today's limits reject: keep the key order
    return [
        CaseOut(
            id=row.case_key,
            input=row.input,
            call=row.call,
            attack=row.attack_type,
            context_count=len((row.context or {}).get("documents", [])),
            judges=row.expectations.get("judges", []),
        )
        for row in rows
    ]


def _version_exists(suite: Suite, version: int) -> bool:
    return 1 <= version <= suite.version


@router.post("/suites/validate")
async def validate_suite(body: SuiteIn, principal: CurrentPrincipal) -> SuiteValidateOut:
    try:
        parsed = parse_suite_yaml(body.yaml)
    except SuiteParseError as exc:
        return SuiteValidateOut(valid=False, issues=exc.issues)
    return SuiteValidateOut(valid=True, case_count=len(parsed.cases))
