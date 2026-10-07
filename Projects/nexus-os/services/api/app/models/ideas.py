"""Ideas (migration 0007): the person's own ideas, notes and to-dos. Separate from memory, which is what
the agents know; these are things the person wants to keep track of."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UTCDateTime


class Idea(TimestampMixin, Base):
    __tablename__ = "ideas"
    __table_args__ = (Index("ix_ideas_status_due_at", "status", "due_at"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # idea | note | todo
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # open | done
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)  # due reminder sent
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    objective_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # started as an objective
