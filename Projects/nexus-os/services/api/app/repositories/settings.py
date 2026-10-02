"""User settings (single row) and notifications."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.foundation import Notification, UserSettings


class UserSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self) -> UserSettings:
        row = await self.session.get(UserSettings, 1)
        if row is None:
            row = UserSettings(id=1)
            self.session.add(row)
            await self.session.flush()
        return row


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, notification: Notification) -> Notification:
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_all(self, *, unread_only: bool = False, limit: int = 100) -> Sequence[Notification]:
        stmt = select(Notification).order_by(Notification.id.desc()).limit(limit)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        return (await self.session.execute(stmt)).scalars().all()

    async def mark_read(self, notification_id: str, when: datetime) -> Notification | None:
        row = await self.session.get(Notification, notification_id)
        if row is not None and row.read_at is None:
            row.read_at = when
        return row

    async def mark_all_read(self, when: datetime) -> int:
        result = await self.session.execute(
            update(Notification).where(Notification.read_at.is_(None)).values(read_at=when)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def unread_count(self) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Notification).where(Notification.read_at.is_(None))
        return int((await self.session.execute(stmt)).scalar_one())
