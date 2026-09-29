"""User settings use cases."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.clock import Clock
from app.core.errors import ConflictError, InvalidRequestError
from app.core.settings import Settings
from app.events.bus import EventBus
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import UserSettings
from app.repositories.projects import ProjectRepository
from app.repositories.settings import UserSettingsRepository
from app.schemas.common import PermissionLevel
from app.schemas.projects import UserSettingsOut, UserSettingsUpdate

log = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, db: Database, bus: EventBus, settings: Settings, clock: Clock) -> None:
        self._db = db
        self._bus = bus
        self._settings = settings
        self._clock = clock

    def _to_out(self, row: UserSettings) -> UserSettingsOut:
        return UserSettingsOut(
            display_name=row.display_name,
            workspace_root=row.workspace_root or str(self._settings.default_workspace_root),
            default_permission_level=PermissionLevel(row.default_permission_level),
            onboarding_completed=row.onboarding_completed,
            preferences=row.preferences,
            updated_at=row.updated_at,
        )

    async def get(self) -> UserSettingsOut:
        async with self._db.session() as session:
            return self._to_out(await UserSettingsRepository(session).get_or_create())

    async def workspace_root(self) -> Path:
        return Path((await self.get()).workspace_root)

    async def default_permission_level(self) -> PermissionLevel:
        return (await self.get()).default_permission_level

    async def update(self, patch: UserSettingsUpdate, *, actor: str = "user") -> UserSettingsOut:
        changes = patch.model_dump(exclude_unset=True)
        changed: list[str] = []
        async with self._db.session() as session:
            row = await UserSettingsRepository(session).get_or_create()
            if "workspace_root" in changes and changes["workspace_root"] is not None:
                new_root = self._validate_workspace_root(changes["workspace_root"])
                current = row.workspace_root or str(self._settings.default_workspace_root)
                if str(new_root) != current:
                    if await ProjectRepository(session).count() > 0:
                        raise ConflictError(
                            "The workspace folder cannot change once projects exist, because their "
                            "files live inside it. Create a new project instead."
                        )
                    row.workspace_root = str(new_root)
                    changed.append("workspace_root")
            for key in ("display_name", "default_permission_level", "onboarding_completed"):
                if key in changes and changes[key] is not None:
                    value = changes[key]
                    value = value.value if isinstance(value, PermissionLevel) else value
                    if getattr(row, key) != value:
                        setattr(row, key, value)
                        changed.append(key)
            if "preferences" in changes and changes["preferences"] is not None:
                row.preferences = {**row.preferences, **changes["preferences"]}
                changed.append("preferences")
            row.updated_at = self._clock.now()
            out = self._to_out(row)
        if changed:
            await self._bus.emit(
                EventType.SETTINGS_UPDATED, actor=actor, payload={"changed": sorted(changed)}
            )
        return out

    def _validate_workspace_root(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise InvalidRequestError("The workspace folder must be an absolute path.")
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".nexus-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise InvalidRequestError(f"The workspace folder is not writable: {exc.strerror}") from exc
        return path.resolve()
