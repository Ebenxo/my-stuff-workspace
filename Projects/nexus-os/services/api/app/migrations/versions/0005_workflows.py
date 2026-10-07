"""workflows and schedules

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29 19:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflows")),
    )
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workflows_project_id"), ["project_id"], unique=False)

    op.create_table(
        "workflow_versions",
        sa.Column("workflow_id", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name=op.f("fk_workflow_versions_workflow_id_workflows"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workflow_id", "version", name=op.f("pk_workflow_versions")),
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workflow_id", sa.String(length=40), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("unattended", sa.Boolean(), nullable=False),
        sa.Column("schedule_id", sa.String(length=40), nullable=True),
        sa.Column("parent_run_id", sa.String(length=40), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("node_states", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_workflow_runs_project_id"), ["project_id"], unique=False)
        batch_op.create_index("ix_workflow_runs_status", ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_workflow_runs_workflow_id"), ["workflow_id"], unique=False)

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("workflow_id", sa.String(length=40), nullable=False),
        sa.Column("cron", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_id", sa.String(length=40), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedules")),
    )
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_schedules_next_run_at"), ["next_run_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_schedules_workflow_id"), ["workflow_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("schedules", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_schedules_workflow_id"))
        batch_op.drop_index(batch_op.f("ix_schedules_next_run_at"))
    op.drop_table("schedules")
    with op.batch_alter_table("workflow_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflow_runs_workflow_id"))
        batch_op.drop_index("ix_workflow_runs_status")
        batch_op.drop_index(batch_op.f("ix_workflow_runs_project_id"))
    op.drop_table("workflow_runs")
    op.drop_table("workflow_versions")
    with op.batch_alter_table("workflows", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_workflows_project_id"))
    op.drop_table("workflows")
