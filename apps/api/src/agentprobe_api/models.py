"""SQLAlchemy models: SPEC.md §7 with the changes in PLAN.md §3 and ADR 0007."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    MetaData,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agentprobe_api.settings import get_settings

Money = Numeric(12, 6)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_N_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {  # noqa: RUF012
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
    }


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


def _fk(target: str, *, index: bool = True, nullable: bool = False) -> Mapped[Any]:
    """CASCADE FK. index=False only where a composite unique/PK already leads with it."""
    return mapped_column(ForeignKey(target, ondelete="CASCADE"), index=index, nullable=nullable)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    created_at: Mapped[datetime] = _created_at()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    name: Mapped[str]
    description: Mapped[str | None]


class ApiKey(Base):
    """`ap_…` project keys. Only the SHA-256 and the last 4 chars are stored (ADR 0009)."""

    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    key_hash: Mapped[str] = mapped_column(unique=True)
    last4: Mapped[str]
    label: Mapped[str]
    created_at: Mapped[datetime] = _created_at()
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]


class RefreshToken(Base):
    """Opaque refresh tokens, stored hashed, rotated on every use (ADR 0009)."""

    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = _fk("users.id")
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()


class Secret(Base):
    """Fernet ciphertext only (ADR 0003). Never returned by the API or logged."""

    __tablename__ = "secrets"
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id")
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = _created_at()


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        CheckConstraint("adapter_type IN ('http', 'mcp', 'python')", name="adapter_type"),
    )
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id", index=False)
    name: Mapped[str]
    adapter_type: Mapped[str]
    config: Mapped[dict[str, Any]]
    secret_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("secrets.id", ondelete="SET NULL"), index=True
    )


class Suite(Base):
    __tablename__ = "suites"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id", index=False)
    name: Mapped[str]
    yaml_source: Mapped[str]
    version: Mapped[int]
    created_at: Mapped[datetime] = _created_at()


class TestCase(Base):
    """Immutable per suite version (PLAN §2 #1)."""

    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("suite_id", "suite_version", "case_key"),)
    __test__ = False  # not a pytest class
    id: Mapped[uuid.UUID] = _pk()
    suite_id: Mapped[uuid.UUID] = _fk("suites.id", index=False)
    suite_version: Mapped[int]
    case_key: Mapped[str]
    input: Mapped[str | None]  # MCP cases use `call` instead
    attack_type: Mapped[str | None]
    expectations: Mapped[dict[str, Any]]
    context: Mapped[dict[str, Any] | None]
    call: Mapped[dict[str, Any] | None]


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="status"
        ),
        Index("ix_runs_suite_id_created_at", "suite_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = _pk()
    # Covered by ix_runs_suite_id_created_at.
    suite_id: Mapped[uuid.UUID] = _fk("suites.id", index=False)
    suite_version: Mapped[int]
    agent_id: Mapped[uuid.UUID] = _fk("agents.id")
    status: Mapped[str] = mapped_column(index=True)  # recovery scans by status
    git_sha: Mapped[str | None]
    branch: Mapped[str | None]
    pr_number: Mapped[int | None]
    model: Mapped[str | None]  # user label for the agent's model
    runs_per_case: Mapped[int]
    mock_mode: Mapped[bool]
    config_snapshot: Mapped[dict[str, Any]]  # suite YAML + agent config at run start
    error: Mapped[str | None]
    attempts_total: Mapped[int]
    attempts_done: Mapped[int] = mapped_column(server_default="0")
    heartbeat_at: Mapped[datetime | None]  # last persisted attempt; stale runs are recovered
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    pass_rate: Mapped[float | None]
    ci_lower: Mapped[float | None]
    ci_upper: Mapped[float | None]
    total_cost: Mapped[Decimal | None] = mapped_column(Money)  # the agent's own spend
    total_tokens: Mapped[int | None]
    judge_cost_usd: Mapped[Decimal | None] = mapped_column(Money)
    share_token_hash: Mapped[str | None] = mapped_column(unique=True)  # SHA-256, never the token
    share_expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = _created_at()


class RunResult(Base):
    __tablename__ = "run_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "attempt"),
        CheckConstraint("status IN ('passed', 'failed', 'error')", name="status"),
        CheckConstraint(
            "error_kind IN ('timeout', 'agent', 'unreachable', 'judge', 'budget', 'internal')",
            name="error_kind",
        ),
    )
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = _fk("runs.id", index=False)
    case_id: Mapped[uuid.UUID] = _fk("test_cases.id")
    attempt: Mapped[int]
    status: Mapped[str]
    output: Mapped[str | None]
    latency_ms: Mapped[int | None]
    tokens: Mapped[int | None]
    cost: Mapped[Decimal | None] = mapped_column(Money)  # the agent's own, estimated
    error_kind: Mapped[str | None]
    score: Mapped[float | None]
    judge_cost_usd: Mapped[Decimal | None] = mapped_column(Money)
    retries: Mapped[int] = mapped_column(server_default="0")
    # core's AttemptResult without response.steps (those are in traces): what the server
    # rebuilds the attempt from to finalize or resume a run (ADR 0017).
    detail: Mapped[dict[str, Any]]


class Trace(Base):
    __tablename__ = "traces"
    id: Mapped[uuid.UUID] = _pk()
    run_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("run_results.id", ondelete="CASCADE"), unique=True
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class Judgment(Base):
    """Scoped to one attempt (run_result_id) or to a case in a run (run_id + case_id)."""

    __tablename__ = "judgments"
    __table_args__ = (
        CheckConstraint(
            "(run_result_id IS NOT NULL AND run_id IS NULL AND case_id IS NULL)"
            " OR (run_result_id IS NULL AND run_id IS NOT NULL AND case_id IS NOT NULL)",
            name="one_scope",
        ),
        CheckConstraint("status IN ('pass', 'fail', 'error')", name="status"),
    )
    id: Mapped[uuid.UUID] = _pk()
    run_result_id: Mapped[uuid.UUID | None] = _fk("run_results.id", nullable=True)
    run_id: Mapped[uuid.UUID | None] = _fk("runs.id", nullable=True)
    case_id: Mapped[uuid.UUID | None] = _fk("test_cases.id", nullable=True)
    judge_type: Mapped[str]
    status: Mapped[str]  # error: the judge couldn't evaluate (never a silent pass or fail)
    passed: Mapped[bool]  # status == "pass"
    score: Mapped[float | None]
    reason: Mapped[str | None]
    evidence: Mapped[dict[str, Any]] = mapped_column(server_default="{}")


class RunCaseSummary(Base):
    __tablename__ = "run_case_summaries"
    __table_args__ = (
        CheckConstraint("label IN ('stable-pass', 'stable-fail', 'flaky')", name="label"),
        CheckConstraint("passes >= 0 AND passes <= attempts", name="passes"),
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    attempts: Mapped[int]
    passes: Mapped[int]
    errors: Mapped[int] = mapped_column(server_default="0")
    pass_rate: Mapped[float]
    label: Mapped[str]
    mean_score: Mapped[float | None]
    consistency_score: Mapped[float | None]
    mean_latency_ms: Mapped[float | None]
    total_cost: Mapped[Decimal | None] = mapped_column(Money)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = _fk("runs.id")
    cluster_label: Mapped[str]
    summary: Mapped[str]
    suggested_fix: Mapped[str | None]
    # Dimension is fixed at migration time; changing EMBEDDING_DIM needs a migration.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(get_settings().embedding_dim))
    member_result_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))


class Baseline(Base):
    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("project_id", "branch"),)
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID] = _fk("projects.id", index=False)
    branch: Mapped[str]
    run_id: Mapped[uuid.UUID] = _fk("runs.id")
