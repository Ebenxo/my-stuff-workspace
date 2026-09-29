"""Notifications. In-app today; the sink interface admits desktop push, email, Telegram, Slack."""

from __future__ import annotations

import logging
from typing import Protocol

from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.ids import new_id
from app.events.bus import EventBus
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import Notification
from app.repositories.settings import NotificationRepository
from app.schemas.projects import NotificationOut

log = logging.getLogger(__name__)


class NotificationSink(Protocol):
    name: str

    async def deliver(self, notification: NotificationOut) -> None: ...


class NotificationService:
    def __init__(self, db: Database, bus: EventBus, clock: Clock) -> None:
        self._db = db
        self._bus = bus
        self._clock = clock
        self._sinks: list[NotificationSink] = []

    def add_sink(self, sink: NotificationSink) -> None:
        self._sinks.append(sink)

    async def notify(
        self,
        kind: str,
        title: str,
        body: str = "",
        *,
        project_id: str | None = None,
        ref: dict[str, object] | None = None,
    ) -> NotificationOut:
        async with self._db.session() as session:
            row = await NotificationRepository(session).add(
                Notification(
                    id=new_id("ntf"),
                    kind=kind,
                    title=title[:200],
                    body=body,
                    project_id=project_id,
                    ref=ref or {},
                    created_at=self._clock.now(),
                )
            )
            out = NotificationOut.model_validate(row)
        await self._bus.emit(
            EventType.NOTIFICATION_CREATED,
            project_id=project_id,
            payload={"notification_id": out.id, "kind": kind, "title": out.title},
        )
        for sink in self._sinks:
            try:
                await sink.deliver(out)
            except Exception:
                log.exception("notification sink %s failed", sink.name)
        return out

    async def list_all(self, *, unread_only: bool = False, limit: int = 100) -> list[NotificationOut]:
        async with self._db.session() as session:
            rows = await NotificationRepository(session).list_all(unread_only=unread_only, limit=limit)
            return [NotificationOut.model_validate(r) for r in rows]

    async def unread_count(self) -> int:
        async with self._db.session() as session:
            return await NotificationRepository(session).unread_count()

    async def mark_read(self, notification_id: str) -> NotificationOut:
        async with self._db.session() as session:
            row = await NotificationRepository(session).mark_read(notification_id, self._clock.now())
            if row is None:
                raise NotFoundError(f"Notification {notification_id} not found")
            return NotificationOut.model_validate(row)

    async def mark_all_read(self) -> int:
        async with self._db.session() as session:
            return await NotificationRepository(session).mark_all_read(self._clock.now())
