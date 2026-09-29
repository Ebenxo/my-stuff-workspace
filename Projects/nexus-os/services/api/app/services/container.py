"""Composition root: builds and owns every long-lived object."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.clock import Clock, SystemClock
from app.core.secrets import SecretStore, build_secret_store
from app.core.settings import Settings
from app.events.bus import EventBus
from app.models.database import Database
from app.services.conversations import ConversationService
from app.services.health import HealthService, register_core_checks
from app.services.notifications import NotificationService
from app.services.projects import ProjectService
from app.services.settings import SettingsService
from app.tasks.queue import InProcessJobQueue, JobQueue


@dataclass
class AppContainer:
    settings: Settings
    token: str
    clock: Clock
    db: Database
    bus: EventBus
    secrets: SecretStore
    queue: JobQueue
    settings_service: SettingsService
    projects: ProjectService
    conversations: ConversationService
    notifications: NotificationService
    health: HealthService
    started_at: float

    async def close(self) -> None:
        await self.queue.shutdown()
        await self.bus.close()
        await self.db.close()


async def build_container(
    settings: Settings, *, secrets: SecretStore | None = None, clock: Clock | None = None
) -> AppContainer:
    clock = clock or SystemClock()
    settings.ensure_home()
    token = settings.resolve_api_token()
    db = Database(settings.db_url)
    bus = EventBus(db, clock)
    queue = InProcessJobQueue(concurrency=4)
    secret_store = secrets or build_secret_store(settings.home)
    settings_service = SettingsService(db, bus, settings, clock)
    projects = ProjectService(db, bus, settings_service, clock)
    conversations = ConversationService(db, bus, clock)
    notifications = NotificationService(db, bus, clock)
    health = HealthService()
    started_at = time.monotonic()
    register_core_checks(
        health,
        settings=settings,
        db=db,
        bus=bus,
        queue=queue,
        secrets=secret_store,
        workspace_root=projects.workspace,
        started_at=started_at,
    )
    return AppContainer(
        settings=settings,
        token=token,
        clock=clock,
        db=db,
        bus=bus,
        secrets=secret_store,
        queue=queue,
        settings_service=settings_service,
        projects=projects,
        conversations=conversations,
        notifications=notifications,
        health=health,
        started_at=started_at,
    )
