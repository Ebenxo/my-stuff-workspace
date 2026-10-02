"""ideas, notes and to-dos

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 05:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ideas",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("reminded_at", sa.DateTime(), nullable=True),
        sa.Column("done_at", sa.DateTime(), nullable=True),
        sa.Column("objective_id", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ideas")),
    )
    with op.batch_alter_table("ideas", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ideas_project_id"), ["project_id"], unique=False)
        batch_op.create_index("ix_ideas_status_due_at", ["status", "due_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ideas", schema=None) as batch_op:
        batch_op.drop_index("ix_ideas_status_due_at")
        batch_op.drop_index(batch_op.f("ix_ideas_project_id"))
    op.drop_table("ideas")
