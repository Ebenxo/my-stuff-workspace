"""Application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app import __version__, migrate
from app.api.errors import install_error_handlers
from app.api.middleware import SecurityMiddleware
from app.api.ratelimit import RateLimiter
from app.api.routers import (
    agents,
    approvals,
    artifacts,
    events,
    files,
    health,
    memory,
    notifications,
    objectives,
    projects,
    providers,
    search,
    settings,
    tools,
    usage,
    workflows,
)
from app.core.clock import Clock
from app.core.instance_lock import InstanceLock
from app.core.logging import configure_logging
from app.core.secrets import SecretStore
from app.core.settings import Settings
from app.events.types import EventType
from app.services.container import AppContainer, build_container

log = logging.getLogger(__name__)


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app(
    settings_: Settings | None = None,
    *,
    secrets: SecretStore | None = None,
    clock: Clock | None = None,
    http: httpx.AsyncClient | None = None,
) -> FastAPI:
    cfg = settings_ or Settings()
    configure_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg.ensure_home()
        # Before touching the database: recovery below would disrupt another live instance's runs.
        instance = InstanceLock(cfg.home)
        instance.acquire()
        try:
            await asyncio.to_thread(migrate.upgrade, cfg.sync_db_url)
            container = await build_container(cfg, secrets=secrets, clock=clock, http=http)
            app.state.container = container
            try:
                await container.settings_service.get()  # ensure the settings row exists
                await container.tool_row_store.sync(container.tools.mirror_rows())
                await container.agent_service.sync_builtins()
                await container.agent_service.recover()
                await container.objective_service.recover()  # after runs are marked interrupted
                await container.memory.reembed_stale()  # new items, or a changed embedder
                await container.universal_search.ensure_built()
                await container.workflows.recover()
                if cfg.scheduler_enabled:
                    await container.scheduler.start()
                await container.bus.emit(EventType.SYSTEM_STARTED, payload={"version": __version__})
                log.info("NEXUS API %s ready on %s:%s (home=%s)", __version__, cfg.host, cfg.port, cfg.home)
                yield
            finally:
                await container.close()
        finally:
            instance.release()

    app = FastAPI(
        title="NEXUS OS API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=_operation_id,
        separate_input_output_schemas=False,
        # No trailing-slash redirects: they point at the API's own origin, so a browser behind the dev
        # proxy (or any other origin) would follow them without its token. A wrong path is a 404.
        redirect_slashes=False,
    )
    install_error_handlers(app)
    for module in (
        health,
        settings,
        projects,
        notifications,
        objectives,
        events,
        providers,
        usage,
        agents,
        approvals,
        tools,
        artifacts,
        files,
        memory,
        search,
        workflows,
    ):
        app.include_router(module.router)

    # Middleware order: the last one added is outermost. CORS must wrap the security layer so
    # preflight requests are answered before token checks.
    app.add_middleware(
        SecurityMiddleware,
        token=cfg.resolve_api_token(),
        allowed_hosts=cfg.allowed_hosts,
        allowed_origins=cfg.allowed_origins,
        limiter=RateLimiter(cfg.rate_limit_enabled),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "last-event-id"],
        allow_credentials=False,
        max_age=600,
    )
    return app


def get_container_from(app: FastAPI) -> AppContainer:
    container: AppContainer = app.state.container
    return container
