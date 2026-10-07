from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.core.secrets import MemorySecretStore
from app.core.settings import Settings
from app.main import create_app

TOKEN = "test-token-0123456789abcdef0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        home=tmp_path / "home",
        port=free_port(),
        api_token=TOKEN,  # type: ignore[arg-type]
        rate_limit_enabled=False,
        scheduler_enabled=False,
        _env_file=None,  # type: ignore[call-arg]
    )


class Upstream:
    """Mock internet for provider calls: route by hostname, record every request."""

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[httpx.Request] = []

    def on(self, host: str, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handlers[host] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.handlers.get(request.url.host)
        if handler is None:
            return httpx.Response(502, json={"error": {"message": f"no mock for {request.url.host}"}})
        return handler(request)


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def secret_store() -> MemorySecretStore:
    return MemorySecretStore()


@pytest.fixture
async def app(
    settings: Settings, upstream: Upstream, secret_store: MemorySecretStore
) -> AsyncIterator[FastAPI]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream), follow_redirects=False)
    application = create_app(settings, secrets=secret_store, http=http)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://127.0.0.1:{settings.port}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as c:
        yield c


@pytest.fixture
async def anon_client(app: FastAPI, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=f"http://127.0.0.1:{settings.port}") as c:
        yield c
