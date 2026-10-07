"""Integrations (migration 0006): MCP servers the person added. Secret values never live here: the
config names them, and the values are in the secret store."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("kind", "name", name="uq_integrations_kind_name"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # "mcp"
    name: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_health: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
