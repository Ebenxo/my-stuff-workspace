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
from app.api.routers import events, health, notifications, projects, providers, settings, usage
from app.core.clock import Clock
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
        await asyncio.to_thread(migrate.upgrade, cfg.sync_db_url)
        container = await build_container(cfg, secrets=secrets, clock=clock, http=http)
        app.state.container = container
        await container.settings_service.get()  # ensure the settings row exists
        await container.bus.emit(EventType.SYSTEM_STARTED, payload={"version": __version__})
        log.info("NEXUS API %s ready on %s:%s (home=%s)", __version__, cfg.host, cfg.port, cfg.home)
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(
        title="NEXUS OS API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=_operation_id,
        separate_input_output_schemas=False,
    )
    install_error_handlers(app)
    for module in (health, settings, projects, notifications, events, providers, usage):
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
