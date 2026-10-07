"""Anthropic Messages API adapter."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.base import (
    LLMProvider,
    loads_or_raise,
    parse_json,
    raise_for_status,
    wrap_transport_error,
)
from app.providers.errors import ProviderError, ProviderRefusal
from app.providers.sse import iter_sse
from app.providers.types import (
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    TokenUsage,
)

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
THINKING_BUDGET = {"light": 2048, "deep": 8192}
STRUCTURED_TOOL = "respond"


class AnthropicProvider(LLMProvider):
    kind = "anthropic"

    def __init__(
        self,
        provider_id: str,
        client: httpx.AsyncClient,
        *,
        api_key: str | None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(provider_id, client)
        self._key = api_key
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"anthropic-version": API_VERSION, "content-type": "application/json"}
        if self._key:
            headers["x-api-key"] = self._key
        return headers

    def _body(self, req: GenerateRequest, *, stream: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        }
        if req.system:
            body["system"] = req.system
        if req.stop:
            body["stop_sequences"] = req.stop
        if req.reasoning != "off":
            budget = THINKING_BUDGET[req.reasoning]
            body["thinking"] = {"type": "enabled", "budget_tokens": budget}
            body["max_tokens"] = max(req.max_tokens, budget + 1024)
            # Extended thinking requires the default temperature.
        elif req.temperature is not None:
            body["temperature"] = req.temperature
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _usage(payload: dict[str, Any] | None) -> TokenUsage:
        usage = (payload or {}).get("usage") or {}
        return TokenUsage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )

    async def _post(self, path: str, body: dict[str, Any], model: str | None) -> dict[str, Any]:
        try:
            response = await self._client.post(f"{self._base}{path}", headers=self._headers(), json=body)
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Anthropic") from exc
        raise_for_status(response, model=model)
        result: dict[str, Any] = parse_json(response)
        return result

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        started = time.monotonic()
        data = await self._post("/v1/messages", self._body(req), req.model)
        # Thinking blocks are discarded here and never leave the adapter.
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        if data.get("stop_reason") == "refusal":
            raise ProviderRefusal("The model declined to answer this request.")
        return GenerateResult(
            text=text,
            usage=self._usage(data),
            model=data.get("model", req.model),
            finish_reason=data.get("stop_reason"),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        usage = TokenUsage()
        try:
            async with self._client.stream(
                "POST",
                f"{self._base}/v1/messages",
                headers=self._headers(),
                json=self._body(req, stream=True),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status(response, model=req.model)
                async for event, raw in iter_sse(response):
                    if event == "ping":
                        continue
                    payload = loads_or_raise(raw)
                    kind = payload.get("type")
                    if kind == "message_start":
                        usage.input_tokens = int(
                            (payload.get("message", {}).get("usage") or {}).get("input_tokens") or 0
                        )
                    elif kind == "content_block_delta":
                        delta = payload.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamChunk(kind="text", text=delta.get("text", ""))
                    elif kind == "message_delta":
                        usage.output_tokens = int(
                            (payload.get("usage") or {}).get("output_tokens") or usage.output_tokens
                        )
                    elif kind == "error":
                        raise ProviderError(
                            str(payload.get("error", {}).get("message", "stream error"))[:300]
                        )
                    elif kind == "message_stop":
                        break
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Anthropic") from exc
        yield StreamChunk(kind="usage", usage=usage)
        yield StreamChunk(kind="done")

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        if req.reasoning != "off":
            # Forced tool use is incompatible with extended thinking: fall back to schema-in-prompt.
            return await super()._structured_call(req, json_schema, name)
        started = time.monotonic()
        body = self._body(req)
        body["tools"] = [
            {
                "name": STRUCTURED_TOOL,
                "description": f"Return the final {name} result.",
                "input_schema": json_schema,
            }
        ]
        body["tool_choice"] = {"type": "tool", "name": STRUCTURED_TOOL}
        data = await self._post("/v1/messages", body, req.model)
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == STRUCTURED_TOOL:
                return GenerateResult(
                    text=json.dumps(block.get("input", {})),
                    usage=self._usage(data),
                    model=data.get("model", req.model),
                    finish_reason=data.get("stop_reason"),
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return GenerateResult(text=text, usage=self._usage(data), model=data.get("model", req.model))

    async def count_tokens(self, req: GenerateRequest) -> int:
        body = {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        }
        if req.system:
            body["system"] = req.system
        try:
            data = await self._post("/v1/messages/count_tokens", body, req.model)
            return int(data.get("input_tokens", 0))
        except ProviderError:
            return await super().count_tokens(req)

    async def available_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(
                f"{self._base}/v1/models", headers=self._headers(), params={"limit": 100}
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Anthropic") from exc
        raise_for_status(response)
        return [
            ModelInfo(id=m["id"], provider_id=self.provider_id, display_name=m.get("display_name"))
            for m in parse_json(response).get("data", [])
            if "id" in m
        ]
