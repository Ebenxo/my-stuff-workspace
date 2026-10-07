"""SSE through a real HTTP server (ASGI test transports buffer streaming bodies)."""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import uvicorn

from app.core.secrets import MemorySecretStore
from app.core.settings import Settings
from app.events.types import EventType
from app.main import create_app
from tests.conftest import TOKEN


async def test_live_sse_over_http_with_resume(settings: Settings) -> None:
    app = create_app(settings, secrets=MemorySecretStore())
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="warning", lifespan="on")
    )
    serve = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        bus = app.state.container.bus
        base = f"http://127.0.0.1:{settings.port}"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        first = await bus.emit(EventType.TASK_CREATED, project_id="proj_live", payload={"i": 0})
        await bus.emit(EventType.TASK_CREATED, project_id="proj_live", payload={"i": 1})

        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=10) as c:
            # unauthenticated stream is refused
            async with httpx.AsyncClient(base_url=base) as anon:
                assert (await anon.get("/api/events/stream")).status_code == 401

            received: list[str] = []
            async with c.stream(
                "GET",
                "/api/events/stream",
                params={"project_id": "proj_live"},
                headers={"Last-Event-ID": str(first.seq)},
            ) as resp:
                assert resp.status_code == 200
                assert resp.headers["content-type"].startswith("text/event-stream")
                publisher = asyncio.create_task(_publish_later(bus))
                async for line in resp.aiter_lines():
                    if line.startswith("id: "):
                        received.append(line.removeprefix("id: "))
                    if len(received) == 2:
                        break
                await publisher
            assert int(received[0]) == first.seq + 1
            assert int(received[1]) == first.seq + 2
    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(serve, 10)


async def _publish_later(bus) -> None:  # type: ignore[no-untyped-def]
    await asyncio.sleep(0.2)
    await bus.emit(EventType.TASK_CREATED, project_id="proj_live", payload={"i": 2})
