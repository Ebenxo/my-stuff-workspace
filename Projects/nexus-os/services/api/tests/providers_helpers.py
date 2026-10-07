from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class Recorder:
    """A mock upstream that records requests and replies from a queue of responses."""

    def __init__(self, *responses: httpx.Response | Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            return httpx.Response(500, json={"error": {"message": "no more scripted responses"}})
        nxt = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return nxt(request) if callable(nxt) else nxt

    def body(self, index: int = -1) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.requests[index].content)
        return result


def sse(*events: tuple[str, dict[str, Any] | str]) -> httpx.Response:
    lines: list[str] = []
    for name, data in events:
        if name:
            lines.append(f"event: {name}")
        lines.append(f"data: {data if isinstance(data, str) else json.dumps(data)}")
        lines.append("")
    return httpx.Response(
        200, content="\n".join(lines).encode(), headers={"content-type": "text/event-stream"}
    )


class Answer(BaseModel):
    city: str
    population_millions: float
