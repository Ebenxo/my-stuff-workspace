"""System health. Later phases register their own checks; the report aggregates them."""

from __future__ import annotations

import logging
import platform
import sys
import time
from collections.abc import Awaitable, Callable

from app import __version__, migrate
from app.core.secrets import SecretStore
from app.core.settings import Settings
from app.events.bus import EventBus
from app.files.workspace import WorkspaceManager
from app.models.database import Database
from app.providers.registry import ProviderRegistry
from app.schemas.health import HealthCheckResult, HealthReport, HealthStatus
from app.tasks.queue import JobQueue

log = logging.getLogger(__name__)

HealthCheck = Callable[[], Awaitable[HealthCheckResult]]
_ORDER: dict[HealthStatus, int] = {"ok": 0, "unavailable": 0, "degraded": 1, "down": 2}


class HealthService:
    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}

    def register(self, name: str, check: HealthCheck) -> None:
        self._checks[name] = check

    async def report(self) -> HealthReport:
        results: list[HealthCheckResult] = []
        for name, check in self._checks.items():
            try:
                results.append(await check())
            except Exception as exc:
                log.exception("health check %s failed", name)
                results.append(
                    HealthCheckResult(
                        name=name,
                        label=name,
                        status="down",
                        detail=f"check raised {type(exc).__name__}",
                    )
                )
        worst = max((r.status for r in results), key=lambda s: _ORDER[s], default="ok")
        return HealthReport(status=worst, version=__version__, checks=results)


def register_core_checks(
    health: HealthService,
    *,
    settings: Settings,
    db: Database,
    bus: EventBus,
    queue: JobQueue,
    secrets: SecretStore,
    workspace_root: Callable[[], Awaitable[WorkspaceManager]],
    started_at: float,
    registry: ProviderRegistry,
) -> None:
    async def backend() -> HealthCheckResult:
        return HealthCheckResult(
            name="backend",
            label="Backend",
            status="ok",
            detail=f"NEXUS API {__version__}",
            data={
                "version": __version__,
                "uptime_s": round(time.monotonic() - started_at, 1),
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "bind": f"{settings.host}:{settings.port}",
            },
        )

    async def database() -> HealthCheckResult:
        await db.ping()
        url = settings.sync_db_url
        current, head = migrate.current_revision(url), migrate.head_revision(url)
        path = db.sqlite_path
        size = path.stat().st_size if path and path.exists() else 0
        if current != head:
            return HealthCheckResult(
                name="database",
                label="Database",
                status="degraded",
                detail=f"schema {current} is behind {head}; run migrations",
                data={"revision": current, "head": head},
            )
        return HealthCheckResult(
            name="database",
            label="Database",
            status="ok",
            detail=f"SQLite, schema {current}",
            data={"revision": current, "size_bytes": size, "path": str(path) if path else None},
        )

    async def events() -> HealthCheckResult:
        latest = await bus.latest_seq()
        return HealthCheckResult(
            name="events",
            label="Event log",
            status="ok",
            detail=f"{latest} events recorded",
            data={"latest_seq": latest, "live_subscribers": bus.subscriber_count},
        )

    async def queue_check() -> HealthCheckResult:
        s = queue.stats()
        status: HealthStatus = "degraded" if s.failed and s.failed > s.completed else "ok"
        return HealthCheckResult(
            name="queue",
            label="Background queue",
            status=status,
            detail=f"{s.running} running, {s.pending} pending",
            data={
                "pending": s.pending,
                "running": s.running,
                "completed": s.completed,
                "failed": s.failed,
                "concurrency": s.concurrency,
            },
        )

    async def disk() -> HealthCheckResult:
        usage = (await workspace_root()).disk_usage()
        free_pct = usage.free / usage.total * 100 if usage.total else 0
        status: HealthStatus = "down" if free_pct < 2 else "degraded" if free_pct < 10 else "ok"
        return HealthCheckResult(
            name="disk",
            label="Disk",
            status=status,
            detail=f"{usage.free / 1e9:.1f} GB free; workspace {usage.workspace_bytes / 1e6:.1f} MB",
            data={
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "workspace_bytes": usage.workspace_bytes,
            },
        )

    async def secret_store() -> HealthCheckResult:
        status: HealthStatus = "ok" if secrets.kind == "keyring" else "degraded"
        return HealthCheckResult(
            name="secrets",
            label="Secret storage",
            status=status,
            detail=secrets.describe(),
            data={"kind": secrets.kind},
        )

    async def providers_check() -> HealthCheckResult:
        rows = await registry.configs(enabled_only=True)
        if not rows:
            return HealthCheckResult(
                name="providers",
                label="AI providers",
                status="unavailable",
                detail="No AI provider configured. Add one in Settings → AI Providers.",
                data={"enabled": 0},
            )
        failing = [r.name for r in rows if r.last_test_ok is False]
        untested = [r.name for r in rows if r.last_test_ok is None]
        status: HealthStatus = "degraded" if failing else "ok"
        detail = f"{len(rows)} enabled"
        if failing:
            detail += f"; last test failed for {', '.join(failing)}"
        elif untested:
            detail += f"; not yet tested: {', '.join(untested)}"
        return HealthCheckResult(
            name="providers",
            label="AI providers",
            status=status,
            detail=detail,
            data={"enabled": len(rows), "failing": len(failing), "untested": len(untested)},
        )

    for name, fn in (
        ("backend", backend),
        ("database", database),
        ("events", events),
        ("queue", queue_check),
        ("disk", disk),
        ("secrets", secret_store),
        ("providers", providers_check),
    ):
        health.register(name, fn)
