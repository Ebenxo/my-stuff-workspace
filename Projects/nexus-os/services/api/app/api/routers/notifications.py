from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.projects import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    c: Container, unread_only: bool = False, limit: int = 100
) -> list[NotificationOut]:
    return await c.notifications.list_all(unread_only=unread_only, limit=min(max(limit, 1), 500))


@router.get("/unread-count")
async def unread_count(c: Container) -> dict[str, int]:
    return {"count": await c.notifications.unread_count()}


@router.post("/read-all")
async def read_all(c: Container) -> dict[str, int]:
    return {"marked": await c.notifications.mark_all_read()}


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(notification_id: str, c: Container) -> NotificationOut:
    return await c.notifications.mark_read(notification_id)
