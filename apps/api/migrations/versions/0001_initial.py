"""Initial schema: SPEC.md §7 + PLAN.md §3 + ADR 0007.

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from agentprobe_api.settings import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [  # creation order; dropped in reverse
    "users",
    "projects",
    "api_keys",
    "secrets",
    "suites",
    "agents",
    "test_cases",
    "runs",
    "baselines",
    "findings",
    "run_case_summaries",
    "run_results",
    "judgments",
    "traces",
]


def _id() -> sa.Column[Any]:
    return sa.Column("id", sa.UUID(), nullable=False)


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "projects",
        _id(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_projects_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"])
    op.create_table(
        "api_keys",
        _id(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_api_keys_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index(op.f("ix_api_keys_project_id"), "api_keys", ["project_id"])
    op.create_table(
        "secrets",
        _id(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_secrets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secrets")),
    )
    op.create_index(op.f("ix_secrets_project_id"), "secrets", ["project_id"])
    op.create_table(
        "suites",
        _id(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("yaml_source", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_suites_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suites")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_suites_project_id_name")),
    )
    op.create_table(
        "agents",
        _id(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("adapter_type", sa.String(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("secret_ref", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "adapter_type IN ('http', 'mcp', 'python')", name=op.f("ck_agents_adapter_type")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_agents_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["secret_ref"],
            ["secrets.id"],
            name=op.f("fk_agents_secret_ref_secrets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_agents_project_id_name")),
    )
    op.create_index(op.f("ix_agents_secret_ref"), "agents", ["secret_ref"])
    op.create_table(
        "test_cases",
        _id(),
        sa.Column("suite_id", sa.UUID(), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("case_key", sa.String(), nullable=False),
        sa.Column("input", sa.String(), nullable=True),
        sa.Column("attack_type", sa.String(), nullable=True),
        sa.Column("expectations", postgresql.JSONB(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("call", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["suites.id"],
            name=op.f("fk_test_cases_suite_id_suites"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_cases")),
        sa.UniqueConstraint(
            "suite_id",
            "suite_version",
            "case_key",
            name=op.f("uq_test_cases_suite_id_suite_version_case_key"),
        ),
    )
    op.create_table(
        "runs",
        _id(),
        sa.Column("suite_id", sa.UUID(), nullable=False),
        sa.Column("suite_version", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("git_sha", sa.String(), nullable=True),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("runs_per_case", sa.Integer(), nullable=False),
        sa.Column("mock_mode", sa.Boolean(), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("judge_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("share_token_hash", sa.String(), nullable=True),
        sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name=op.f("ck_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_runs_agent_id_agents"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"], ["suites.id"], name=op.f("fk_runs_suite_id_suites"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.UniqueConstraint("share_token_hash", name=op.f("uq_runs_share_token_hash")),
    )
    op.create_index(op.f("ix_runs_agent_id"), "runs", ["agent_id"])
    op.create_index("ix_runs_suite_id_created_at", "runs", ["suite_id", "created_at"])
    op.create_table(
        "baselines",
        _id(),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_baselines_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_baselines_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_baselines")),
        sa.UniqueConstraint("project_id", "branch", name=op.f("uq_baselines_project_id_branch")),
    )
    op.create_index(op.f("ix_baselines_run_id"), "baselines", ["run_id"])
    op.create_table(
        "findings",
        _id(),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("cluster_label", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("suggested_fix", sa.String(), nullable=True),
        # Fixed at migration time from EMBEDDING_DIM; changing it needs a new migration.
        sa.Column("embedding", Vector(get_settings().embedding_dim), nullable=True),
        sa.Column("member_result_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_findings_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
    )
    op.create_index(op.f("ix_findings_run_id"), "findings", ["run_id"])
    op.create_table(
        "run_case_summaries",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("passes", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("mean_score", sa.Float(), nullable=True),
        sa.Column("consistency_score", sa.Float(), nullable=True),
        sa.Column("mean_latency_ms", sa.Float(), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.CheckConstraint(
            "label IN ('stable-pass', 'stable-fail', 'flaky')",
            name=op.f("ck_run_case_summaries_label"),
        ),
        sa.CheckConstraint(
            "passes >= 0 AND passes <= attempts", name=op.f("ck_run_case_summaries_passes")
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["test_cases.id"],
            name=op.f("fk_run_case_summaries_case_id_test_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_run_case_summaries_run_id_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "case_id", name=op.f("pk_run_case_summaries")),
    )
    op.create_index(op.f("ix_run_case_summaries_case_id"), "run_case_summaries", ["case_id"])
    op.create_table(
        "run_results",
        _id(),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("output", sa.String(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'error')", name=op.f("ck_run_results_status")
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["test_cases.id"],
            name=op.f("fk_run_results_case_id_test_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_results_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_results")),
        sa.UniqueConstraint(
            "run_id", "case_id", "attempt", name=op.f("uq_run_results_run_id_case_id_attempt")
        ),
    )
    op.create_index(op.f("ix_run_results_case_id"), "run_results", ["case_id"])
    op.create_table(
        "judgments",
        _id(),
        sa.Column("run_result_id", sa.UUID(), nullable=True),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("case_id", sa.UUID(), nullable=True),
        sa.Column("judge_type", sa.String(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.CheckConstraint(
            "(run_result_id IS NOT NULL AND run_id IS NULL AND case_id IS NULL)"
            " OR (run_result_id IS NULL AND run_id IS NOT NULL AND case_id IS NOT NULL)",
            name=op.f("ck_judgments_one_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["test_cases.id"],
            name=op.f("fk_judgments_case_id_test_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_judgments_run_id_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_result_id"],
            ["run_results.id"],
            name=op.f("fk_judgments_run_result_id_run_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_judgments")),
    )
    op.create_index(op.f("ix_judgments_case_id"), "judgments", ["case_id"])
    op.create_index(op.f("ix_judgments_run_id"), "judgments", ["run_id"])
    op.create_index(op.f("ix_judgments_run_result_id"), "judgments", ["run_result_id"])
    op.create_table(
        "traces",
        _id(),
        sa.Column("run_result_id", sa.UUID(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_result_id"],
            ["run_results.id"],
            name=op.f("fk_traces_run_result_id_run_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_traces")),
        sa.UniqueConstraint("run_result_id", name=op.f("uq_traces_run_result_id")),
    )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)  # drops its indexes and constraints too
    op.execute("DROP EXTENSION IF EXISTS vector")
