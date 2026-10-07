"""memory and search

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29 18:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Full-text index for universal search. FTS5 ships with Python's SQLite on every supported platform;
# if a build lacks it, a plain table with the same columns is created and search falls back to LIKE.
SEARCH_FTS = (
    "CREATE VIRTUAL TABLE search_index USING fts5("
    "kind UNINDEXED, ref_id UNINDEXED, project_id UNINDEXED, title, body, "
    "tokenize = 'unicode61 remove_diacritics 2')"
)
SEARCH_PLAIN = (
    "CREATE TABLE search_index (kind VARCHAR(20) NOT NULL, ref_id VARCHAR(40) NOT NULL, "
    "project_id VARCHAR(40), title TEXT NOT NULL, body TEXT NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.String(length=40), nullable=True),
        sa.Column("conversation_id", sa.String(length=40), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("merged_into", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_items")),
    )
    with op.batch_alter_table("memory_items", schema=None) as batch_op:
        batch_op.create_index("ix_memory_items_content_hash", ["content_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_memory_items_project_id"), ["project_id"], unique=False)
        batch_op.create_index("ix_memory_items_scope_status", ["scope", "status"], unique=False)

    op.create_table(
        "memory_embeddings",
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("embedder", sa.String(length=60), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["memory_items.id"],
            name=op.f("fk_memory_embeddings_item_id_memory_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("item_id", name=op.f("pk_memory_embeddings")),
    )

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("context_report", sa.JSON(), nullable=True))

    try:
        op.execute(SEARCH_FTS)
    except sa.exc.OperationalError:
        op.execute(SEARCH_PLAIN)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_index")
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_column("context_report")
    op.drop_table("memory_embeddings")
    with op.batch_alter_table("memory_items", schema=None) as batch_op:
        batch_op.drop_index("ix_memory_items_scope_status")
        batch_op.drop_index(batch_op.f("ix_memory_items_project_id"))
        batch_op.drop_index("ix_memory_items_content_hash")
    op.drop_table("memory_items")
