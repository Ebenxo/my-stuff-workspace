"""Memory (migration 0004): remembered items and their embeddings.

The full-text `search_index` table is an FTS5 virtual table created by the migration itself; it has no
ORM model (see `app/repositories/search_index.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime


class MemoryItem(TimestampMixin, Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        Index("ix_memory_items_scope_status", "scope", "status"),
        Index("ix_memory_items_content_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20))  # conversation | project | global
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    # kind (user | agent | objective | summary), agent, run_id, task_id, objective_id, tainted
    source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16))  # active | pending | deleted
    content_hash: Mapped[str] = mapped_column(String(64))
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    merged_into: Mapped[str | None] = mapped_column(String(40), nullable=True)  # set by compression


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    item_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("memory_items.id", ondelete="CASCADE"), primary_key=True
    )
    embedder: Mapped[str] = mapped_column(String(60))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list[float]] = mapped_column(JSON)
