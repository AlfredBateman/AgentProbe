"""Agents CRUD (SPEC.md §4.2, §7). Config is validated per adapter_type; the server refuses
`python` (CLI-only, PLAN.md §2 #14). Auth headers are encrypted into `secrets` (ADR 0003) and
never returned, only whether one is set.
"""

import json
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentprobe_api.auth import CurrentPrincipal, Db, Principal
from agentprobe_api.crypto import SecretBox
from agentprobe_api.errors import ApiError
from agentprobe_api.models import Agent, Project, Secret
from agentprobe_api.projects import owned_project
from agentprobe_core.adapters import HttpAdapterConfig, check_header

router = APIRouter(tags=["agents"])

# --- adapter configs (SPEC.md §4.2) -----------------------------------------------------


class HttpAgentConfig(HttpAdapterConfig):
    """The HTTP adapter's own config (ADR 0012), so what's stored is what the adapter runs."""

    adapter_type: Literal["http"]


class McpAgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter_type: Literal["mcp"]
    server_url: AnyHttpUrl
    tool_timeout_ms: int = Field(default=30_000, gt=0, le=120_000)


class PythonAgentConfig(BaseModel):
    """Accepted so it round-trips through ingested CLI runs; rejected at create/update time
    below because the server can't execute it (PLAN.md §2 #14).
    """

    model_config = ConfigDict(extra="forbid")
    adapter_type: Literal["python"]
    module: str = Field(min_length=1, max_length=500)
    function: str = Field(min_length=1, max_length=200)


AgentConfig = Annotated[
    HttpAgentConfig | McpAgentConfig | PythonAgentConfig, Field(discriminator="adapter_type")
]


def _reject_python_adapter(config: HttpAgentConfig | McpAgentConfig | PythonAgentConfig) -> None:
    if config.adapter_type == "python":
        raise ApiError(400, "The python adapter is CLI-only; the server can't execute it")


# --- request/response models ------------------------------------------------------------


class AuthHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _sendable(self) -> "AuthHeader":
        check_header(self.name, self.value, secret=True)  # its errors never echo the value
        return self


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    config: AgentConfig
    auth_header: AuthHeader | None = None


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: AgentConfig | None = None
    auth_header: AuthHeader | None = None  # set: replaces; omitted: unchanged
    clear_secret: bool = False  # set: removes the stored secret; ignored if auth_header is set


class AgentOut(BaseModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    config: dict[str, Any]
    has_secret: bool


def _agent_out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        adapter_type=agent.adapter_type,
        config=agent.config,
        has_secret=agent.secret_ref is not None,
    )


def _secret_box(request: Request) -> SecretBox:
    box = request.app.state.secret_box
    if box is None:
        raise ApiError(500, "Encryption key is not configured", code="internal_error")
    return box  # type: ignore[no-any-return]


async def owned_agent(db: AsyncSession, principal: Principal, agent_id: uuid.UUID) -> Agent:
    """Not-owned and nonexistent are both 404 (mirrors `owned_project`)."""
    agent = await db.scalar(
        select(Agent)
        .join(Project, Project.id == Agent.project_id)
        .where(Agent.id == agent_id, Project.user_id == principal.user_id)
    )
    if agent is None or (
        principal.project_id is not None and agent.project_id != principal.project_id
    ):
        raise ApiError(404, "Agent not found")
    return agent


async def _store_secret(
    db: AsyncSession, box: SecretBox, project_id: uuid.UUID, auth_header: AuthHeader
) -> uuid.UUID:
    plaintext = json.dumps({"name": auth_header.name, "value": auth_header.value})
    secret = Secret(project_id=project_id, ciphertext=box.encrypt(plaintext))
    db.add(secret)
    await db.flush()
    return secret.id


# --- routes --------------------------------------------------------------------------


@router.post("/projects/{project_id}/agents", status_code=201)
async def create_agent(
    project_id: uuid.UUID, body: AgentIn, principal: CurrentPrincipal, db: Db, request: Request
) -> AgentOut:
    project = await owned_project(db, principal, project_id)
    _reject_python_adapter(body.config)
    secret_ref = None
    if body.auth_header is not None:
        secret_ref = await _store_secret(db, _secret_box(request), project.id, body.auth_header)
    agent = Agent(
        project_id=project.id,
        name=body.name,
        adapter_type=body.config.adapter_type,
        config=body.config.model_dump(mode="json", exclude={"adapter_type"}),
        secret_ref=secret_ref,
    )
    db.add(agent)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "An agent with this name already exists in this project") from exc
    return _agent_out(agent)


@router.get("/projects/{project_id}/agents")
async def list_agents(project_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> list[AgentOut]:
    project = await owned_project(db, principal, project_id)
    agents = await db.scalars(
        select(Agent).where(Agent.project_id == project.id).order_by(Agent.name)
    )
    return [_agent_out(a) for a in agents]


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> AgentOut:
    return _agent_out(await owned_agent(db, principal, agent_id))


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    principal: CurrentPrincipal,
    db: Db,
    request: Request,
) -> AgentOut:
    agent = await owned_agent(db, principal, agent_id)
    if body.config is not None:
        _reject_python_adapter(body.config)
        agent.adapter_type = body.config.adapter_type
        agent.config = body.config.model_dump(mode="json", exclude={"adapter_type"})
    if body.name is not None:
        agent.name = body.name
    if body.auth_header is not None:
        # ponytail: the old secret row (if any) is left orphaned rather than deleted; add a
        # cleanup pass if the secrets table's size ever matters.
        agent.secret_ref = await _store_secret(
            db, _secret_box(request), agent.project_id, body.auth_header
        )
    elif body.clear_secret:
        agent.secret_ref = None
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ApiError(409, "An agent with this name already exists in this project") from exc
    return _agent_out(agent)


@router.delete("/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, principal: CurrentPrincipal, db: Db) -> None:
    agent = await owned_agent(db, principal, agent_id)
    await db.delete(agent)
