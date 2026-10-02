"""Suite versions keep their YAML (ADR 0038).

- suite_versions: one row per (suite, version) with the YAML as uploaded. `suites.yaml_source`
  stays the current version's. Backfilled with each suite's current version; older versions'
  YAML was never stored, so they have case rows but no YAML. A backfilled row's save time is
  known only for version 1 (the suite's own `created_at`); otherwise it is NULL, not a guess.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suite_versions",
        sa.Column("suite_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("yaml_source", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["suites.id"],
            name=op.f("fk_suite_versions_suite_id_suites"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("suite_id", "version", name=op.f("pk_suite_versions")),
    )
    op.execute(
        "INSERT INTO suite_versions (suite_id, version, yaml_source, created_at)"
        " SELECT id, version, yaml_source, CASE WHEN version = 1 THEN created_at END FROM suites"
    )


def downgrade() -> None:
    op.drop_table("suite_versions")
