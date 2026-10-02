"""Minimal SSE / NDJSON readers for provider streaming responses."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx


async def iter_sse(response: httpx.Response) -> AsyncIterator[tuple[str, str]]:
    """Yield ``(event, data)`` pairs from a text/event-stream response."""
    event = ""
    data: list[str] = []
    async for raw in response.aiter_lines():
        line = raw.rstrip("\r")
        if line == "":
            if data:
                yield event or "message", "\n".join(data)
            event, data = "", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
    if data:
        yield event or "message", "\n".join(data)


async def iter_ndjson(response: httpx.Response) -> AsyncIterator[str]:
    async for line in response.aiter_lines():
        if line.strip():
            yield line
