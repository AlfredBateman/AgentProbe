"""Projects and project API keys. Every lookup is scoped resource -> project -> user."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CurrentPrincipal, CurrentUser, Db, Principal
from agentprobe_api.errors import ApiError
from agentprobe_api.models import ApiKey, Project
from agentprobe_api.security import new_api_key, sha256

router = APIRouter(prefix="/projects", tags=["projects"])


async def owned_project(db: AsyncSession, principal: Principal, project_id: uuid.UUID) -> Project:
    """The only way to load a project. Not-owned and nonexistent are both 404, so ids of
    other users' projects can't be probed. An API key only reaches its own project.
    """
    if principal.project_id is not None and principal.project_id != project_id:
        raise ApiError(404, "Project not found")
    project = await db.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == principal.user_id)
    )
    if project is None:
        raise ApiError(404, "Project not found")
    return project


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None


@router.get("")
async def list_projects(principal: CurrentPrincipal, db: Db) -> list[ProjectOut]:
    query = select(Project).where(Project.user_id == principal.user_id).order_by(Project.name)
    if principal.project_id is not None:
        query = query.where(Project.id == principal.project_id)
    return [ProjectOut.model_validate(p) for p in await db.scalars(query)]


@router.post("", status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser, db: Db) -> ProjectOut:
    project = Project(user_id=user.user_id, name=body.name, description=body.description)
    db.add(project)
    await db.flush()
    return ProjectOut.model_validate(project)


@router.get("/{project_id}")
async def get_project(project_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> ProjectOut:
    return ProjectOut.model_validate(await owned_project(db, principal, project_id))


# --- API keys (user sessions only: a key can't mint or revoke keys) --------------------


class ApiKeyIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    label: str
    last4: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyOut):
    key: str  # the only time the full key is ever returned


@router.post("/{project_id}/api-keys", status_code=201)
async def create_api_key(
    project_id: uuid.UUID, body: ApiKeyIn, user: CurrentUser, db: Db
) -> ApiKeyCreated:
    project = await owned_project(db, user, project_id)
    key = new_api_key()
    api_key = ApiKey(project_id=project.id, key_hash=sha256(key), last4=key[-4:], label=body.label)
    db.add(api_key)
    await db.flush()  # RETURNING fills the server-default created_at
    return ApiKeyCreated.model_validate(
        {**ApiKeyOut.model_validate(api_key).model_dump(), "key": key}
    )


@router.get("/{project_id}/api-keys")
async def list_api_keys(project_id: uuid.UUID, user: CurrentUser, db: Db) -> list[ApiKeyOut]:
    project = await owned_project(db, user, project_id)
    keys = await db.scalars(
        select(ApiKey).where(ApiKey.project_id == project.id).order_by(ApiKey.created_at)
    )
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.delete("/{project_id}/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    project_id: uuid.UUID, key_id: uuid.UUID, user: CurrentUser, db: Db
) -> None:
    project = await owned_project(db, user, project_id)
    api_key = await db.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project.id)
    )
    if api_key is None:
        raise ApiError(404, "API key not found")
    if api_key.revoked_at is None:  # idempotent; keep the original revocation time
        api_key.revoked_at = datetime.now(UTC)
