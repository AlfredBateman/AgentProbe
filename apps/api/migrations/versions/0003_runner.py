"""Server runner: progress and recovery columns on runs, and enough on run_results and
judgments to rebuild core's AttemptResult exactly (ADR 0017).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERROR_KINDS = "'timeout', 'agent', 'unreachable', 'judge', 'budget', 'internal'"


def upgrade() -> None:
    # None of these tables has rows yet: no endpoint wrote runs before this revision.
    op.add_column("runs", sa.Column("attempts_total", sa.Integer(), nullable=False))
    op.add_column(
        "runs",
        sa.Column("attempts_done", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("ci_lower", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("ci_upper", sa.Float(), nullable=True))
    op.create_index(op.f("ix_runs_status"), "runs", ["status"])

    op.add_column("run_results", sa.Column("error_kind", sa.String(), nullable=True))
    op.add_column("run_results", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("run_results", sa.Column("judge_cost_usd", sa.Numeric(12, 6), nullable=True))
    op.add_column(
        "run_results",
        sa.Column("retries", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "run_results",
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_run_results_error_kind"), "run_results", f"error_kind IN ({ERROR_KINDS})"
    )

    op.add_column("judgments", sa.Column("status", sa.String(), nullable=False))
    op.add_column(
        "judgments",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_judgments_status"), "judgments", "status IN ('pass', 'fail', 'error')"
    )

    op.add_column(
        "run_case_summaries",
        sa.Column("errors", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("run_case_summaries", "errors")
    op.drop_constraint(op.f("ck_judgments_status"), "judgments", type_="check")
    op.drop_column("judgments", "evidence")
    op.drop_column("judgments", "status")
    op.drop_constraint(op.f("ck_run_results_error_kind"), "run_results", type_="check")
    for column in ("detail", "retries", "judge_cost_usd", "score", "error_kind"):
        op.drop_column("run_results", column)
    op.drop_index(op.f("ix_runs_status"), table_name="runs")
    for column in ("ci_upper", "ci_lower", "heartbeat_at", "attempts_done", "attempts_total"):
        op.drop_column("runs", column)
