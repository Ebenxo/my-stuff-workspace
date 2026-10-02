"""Stored integrations (MCP servers). Returns DTOs; secret values are never stored here."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import new_id
from app.models.database import Database
from app.models.integrations import Integration
from app.schemas.mcp import IntegrationRecord


class IntegrationStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(
        self, *, kind: str, name: str, config: dict[str, Any], enabled: bool, id_: str | None = None
    ) -> IntegrationRecord:
        now = self._clock.now()
        try:
            async with self._db.session() as s:
                row = Integration(
                    id=id_ or new_id(kind),
                    kind=kind,
                    name=name,
                    config=config,
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
                s.add(row)
                await s.flush()
                return IntegrationRecord.model_validate(row)
        except IntegrityError:
            raise ConflictError(f"There is already a server called '{name}'.") from None

    async def get(self, integration_id: str) -> IntegrationRecord:
        async with self._db.session() as s:
            row = await s.get(Integration, integration_id)
            if row is None:
                raise NotFoundError("That server does not exist.")
            return IntegrationRecord.model_validate(row)

    async def list_kind(self, kind: str) -> list[IntegrationRecord]:
        async with self._db.session() as s:
            rows = (
                await s.execute(
                    select(Integration).where(Integration.kind == kind).order_by(Integration.name)
                )
            ).scalars()
            return [IntegrationRecord.model_validate(r) for r in rows]

    async def update(self, integration_id: str, **fields: Any) -> IntegrationRecord:
        async with self._db.session() as s:
            row = await s.get(Integration, integration_id)
            if row is None:
                raise NotFoundError("That server does not exist.")
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = self._clock.now()
            await s.flush()
            return IntegrationRecord.model_validate(row)

    async def delete(self, integration_id: str) -> None:
        async with self._db.session() as s:
            row = await s.get(Integration, integration_id)
            if row is None:
                raise NotFoundError("That server does not exist.")
            await s.delete(row)
