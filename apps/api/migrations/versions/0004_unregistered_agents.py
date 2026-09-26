"""Runs of unregistered agents, and baselines keyed per suite and agent (ADR 0020).

- runs: `agent_id` becomes nullable; `agent_name` names an agent the server has no row for
  (a CLI python-adapter run pushed through /ci/report). Exactly one of the two is set.
- baselines: keyed on (project, suite, branch, agent_id or agent_name) instead of
  (project, branch), so one project can hold a baseline per suite and per agent. Existing
  rows are backfilled from their run.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ONE_AGENT = "(agent_id IS NULL) <> (agent_name IS NULL)"
NEW_KEY = ["project_id", "suite_id", "branch", "agent_id", "agent_name"]


def upgrade() -> None:
    op.alter_column("runs", "agent_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("runs", sa.Column("agent_name", sa.String(), nullable=True))
    op.create_check_constraint(op.f("ck_runs_one_agent"), "runs", ONE_AGENT)

    op.add_column("baselines", sa.Column("suite_id", sa.UUID(), nullable=True))
    op.add_column("baselines", sa.Column("agent_id", sa.UUID(), nullable=True))
    op.add_column("baselines", sa.Column("agent_name", sa.String(), nullable=True))
    op.execute(
        "UPDATE baselines SET suite_id = runs.suite_id, agent_id = runs.agent_id"
        " FROM runs WHERE runs.id = baselines.run_id"
    )
    op.alter_column("baselines", "suite_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key(
        op.f("fk_baselines_suite_id_suites"),
        "baselines",
        "suites",
        ["suite_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_baselines_agent_id_agents"),
        "baselines",
        "agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_baselines_suite_id"), "baselines", ["suite_id"])
    op.create_index(op.f("ix_baselines_agent_id"), "baselines", ["agent_id"])
    op.drop_constraint(op.f("uq_baselines_project_id_branch"), "baselines", type_="unique")
    op.create_unique_constraint(
        op.f("uq_baselines_project_id_suite_id_branch_agent_id_agent_name"),
        "baselines",
        NEW_KEY,
        postgresql_nulls_not_distinct=True,
    )
    op.create_check_constraint(op.f("ck_baselines_one_agent"), "baselines", ONE_AGENT)


def downgrade() -> None:
    # Lossy: the old schema can't hold unregistered-agent runs or more than one baseline
    # per (project, branch), so those rows are dropped (the lowest id per key is kept).
    op.execute("DELETE FROM baselines WHERE agent_id IS NULL")
    op.execute(
        "DELETE FROM baselines b USING baselines o"
        " WHERE b.project_id = o.project_id AND b.branch = o.branch AND b.id > o.id"
    )
    op.drop_constraint(op.f("ck_baselines_one_agent"), "baselines", type_="check")
    op.drop_constraint(
        op.f("uq_baselines_project_id_suite_id_branch_agent_id_agent_name"),
        "baselines",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_baselines_project_id_branch"), "baselines", ["project_id", "branch"]
    )
    op.drop_index(op.f("ix_baselines_agent_id"), table_name="baselines")
    op.drop_index(op.f("ix_baselines_suite_id"), table_name="baselines")
    op.drop_constraint(op.f("fk_baselines_agent_id_agents"), "baselines", type_="foreignkey")
    op.drop_constraint(op.f("fk_baselines_suite_id_suites"), "baselines", type_="foreignkey")
    for column in ("agent_name", "agent_id", "suite_id"):
        op.drop_column("baselines", column)

    op.execute("DELETE FROM runs WHERE agent_id IS NULL")
    op.drop_constraint(op.f("ck_runs_one_agent"), "runs", type_="check")
    op.drop_column("runs", "agent_name")
    op.alter_column("runs", "agent_id", existing_type=sa.UUID(), nullable=False)
