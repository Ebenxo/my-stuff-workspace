from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.projects import UserSettingsOut, UserSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=UserSettingsOut)
async def get_settings(c: Container) -> UserSettingsOut:
    return await c.settings_service.get()


@router.patch("", response_model=UserSettingsOut)
async def update_settings(body: UserSettingsUpdate, c: Container) -> UserSettingsOut:
    return await c.settings_service.update(body)
