"""ScriptedProvider: deterministic replies for tests and the clearly-labelled demo project.

It is NOT a fake for production use: it is registered only as the ``demo`` provider kind, which the
UI labels "Demo (scripted)". It implements the full LLMProvider interface so everything above it
(gateway, agents, orchestrator) runs its real code paths.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from pydantic import BaseModel

from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
from app.providers.types import (
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    TokenUsage,
    estimate_request_tokens,
    estimate_tokens,
)

Reply = str | BaseModel | dict[str, Any] | Exception | Callable[[GenerateRequest], "Reply"]

DEMO_MODEL = "demo:scripted"


class ScriptedProvider(LLMProvider):
    kind = "demo"

    def __init__(self, provider_id: str = "prov_demo", client: httpx.AsyncClient | None = None) -> None:
        super().__init__(provider_id, client)  # type: ignore[arg-type]
        self.requests: list[GenerateRequest] = []
        self.structured_names: list[str | None] = []
        self._queue: deque[Reply] = deque()
        self._handlers: dict[str, Callable[[GenerateRequest], Reply]] = {}

    def push(self, *replies: Reply) -> ScriptedProvider:
        self._queue.extend(replies)
        return self

    def on(
        self, schema: type[BaseModel] | str, handler: Callable[[GenerateRequest], Reply]
    ) -> ScriptedProvider:
        """Answer every structured call for ``schema`` with ``handler`` (takes precedence over the queue)."""
        self._handlers[schema if isinstance(schema, str) else schema.__name__] = handler
        return self

    @property
    def remaining(self) -> int:
        return len(self._queue)

    def _resolve(self, req: GenerateRequest, schema_name: str | None) -> str:
        self.requests.append(req)
        self.structured_names.append(schema_name)
        if schema_name and schema_name in self._handlers:
            reply: Reply = self._handlers[schema_name](req)
        elif self._queue:
            reply = self._queue.popleft()
        else:
            raise ProviderError("ScriptedProvider script exhausted (no reply queued for this call)")
        while callable(reply) and not isinstance(reply, BaseModel | Exception | str | dict):
            reply = reply(req)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, BaseModel):
            return reply.model_dump_json()
        if isinstance(reply, dict):
            return json.dumps(reply)
        return reply

    def _result(self, req: GenerateRequest, text: str) -> GenerateResult:
        return GenerateResult(
            text=text,
            usage=TokenUsage(
                input_tokens=estimate_request_tokens(req), output_tokens=estimate_tokens(text), estimated=True
            ),
            model=req.model,
            finish_reason="stop",
            latency_ms=1,
        )

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        return self._result(req, self._resolve(req, None))

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        return self._result(req, self._resolve(req, name))

    async def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        text = self._resolve(req, None)
        for i in range(0, len(text), 16):
            yield StreamChunk(kind="text", text=text[i : i + 16])
        yield StreamChunk(kind="usage", usage=self._result(req, text).usage)
        yield StreamChunk(kind="done")

    async def available_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id=DEMO_MODEL,
                provider_id=self.provider_id,
                display_name="Demo (scripted)",
                tier="balanced",
                local=True,
                input_cost_per_mtok=0.0,
                output_cost_per_mtok=0.0,
            )
        ]
