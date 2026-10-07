"""integrations (MCP servers) and MCP tool review fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29 23:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_health", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integrations")),
        sa.UniqueConstraint("kind", "name", name="uq_integrations_kind_name"),
    )
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_integrations_kind"), ["kind"], unique=False)
    with op.batch_alter_table("tools", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fingerprint", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tools", schema=None) as batch_op:
        batch_op.drop_column("note")
        batch_op.drop_column("fingerprint")
    with op.batch_alter_table("integrations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_integrations_kind"))
    op.drop_table("integrations")
