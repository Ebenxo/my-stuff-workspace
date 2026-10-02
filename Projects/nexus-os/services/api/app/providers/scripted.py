"""ScriptedProvider: deterministic replies for tests and the clearly-labelled demo project.

It is NOT a fake for production use: it is registered only as the ``demo`` provider kind, which the
UI labels "Demo (scripted)". It implements the full LLMProvider interface so everything above it
(gateway, agents, orchestrator) runs its real code paths.
"""

from __future__ import annotations

import json
import re
from collections import deque
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from pydantic import BaseModel

from app.providers.base import LLMProvider, schema_name
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
        self.fallback: Callable[[GenerateRequest], Reply] | None = None  # e.g. a ScriptBook

    def push(self, *replies: Reply) -> ScriptedProvider:
        self._queue.extend(replies)
        return self

    def on(
        self, schema: type[BaseModel] | str, handler: Callable[[GenerateRequest], Reply]
    ) -> ScriptedProvider:
        """Answer every structured call for ``schema`` with ``handler`` (takes precedence over the queue)."""
        self._handlers[schema if isinstance(schema, str) else schema_name(schema)] = handler
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
        elif self.fallback is not None:
            reply = self.fallback(req)
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


_AGENT_LINE = re.compile(r"^You are the (.+?) agent\.", re.MULTILINE)
_NONCE = re.compile(r'untrusted id="[0-9a-f]+"')


class ScriptBook:
    """Deterministic replies per agent and per turn, for tests and the labelled demo.

    ``add(agent_name, *steps)`` queues one *run* of that agent: its first model turn gets ``steps[0]``,
    its next turn ``steps[1]``, and so on (a repair request counts as a turn). The speaking agent is
    read from the system prompt ("You are the Writer agent."), the turn from the number of assistant
    messages, and a run is identified by its first user message, so parallel runs stay separate.
    """

    def __init__(self) -> None:
        self._pending: dict[str, deque[list[Reply]]] = {}
        self._active: dict[str, list[Reply]] = {}
        self.calls: list[tuple[str, int]] = []

    def add(self, agent: str, *steps: Reply) -> ScriptBook:
        self._pending.setdefault(agent, deque()).append(list(steps))
        return self

    def remaining(self, agent: str | None = None) -> int:
        if agent is not None:
            return len(self._pending.get(agent, ()))
        return sum(len(q) for q in self._pending.values())

    def __call__(self, req: GenerateRequest) -> Reply:
        found = _AGENT_LINE.search(req.system or "")
        agent = found.group(1) if found else "unknown"
        turn = sum(1 for m in req.messages if m.role == "assistant")
        first = next((m.content for m in req.messages if m.role == "user"), "")
        # Untrusted context is fenced with a fresh random nonce on every call; it must not change the key.
        key = f"{agent}\x00{_NONCE.sub('', first)}"
        if turn == 0 or key not in self._active:
            queue = self._pending.get(agent)
            if not queue:
                raise ProviderError(f"No scripted run left for the {agent} agent")
            self._active[key] = queue.popleft()
        script = self._active[key]
        if turn >= len(script):
            raise ProviderError(f"The {agent} agent's script has no step {turn + 1}")
        self.calls.append((agent, turn))
        return script[turn]
