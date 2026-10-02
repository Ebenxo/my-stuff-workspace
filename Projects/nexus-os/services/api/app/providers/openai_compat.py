"""OpenAI Chat Completions adapter. Also serves LM Studio, vLLM and any compatible endpoint."""

from __future__ import annotations

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
from app.providers.errors import ProviderBadRequest, ProviderError, ProviderRefusal
from app.providers.sse import iter_sse
from app.providers.types import (
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    TokenUsage,
)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_FORMAT_HINTS = ("response_format", "json_schema", "json_object", "structured")


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        provider_id: str,
        client: httpx.AsyncClient,
        *,
        kind: str = "openai",
        api_key: str | None,
        base_url: str | None = None,
        structured_mode: str = "json_schema",
    ) -> None:
        super().__init__(provider_id, client)
        self.kind = kind
        self._key = api_key
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        # "json_schema" -> "json_object" -> "prompt": downgraded automatically if the server rejects it.
        self._structured_mode = structured_mode

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        return headers

    def _body(self, req: GenerateRequest, *, stream: bool = False) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)
        body: dict[str, Any] = {"model": req.model, "messages": messages}
        if req.temperature is not None:
            body["temperature"] = req.temperature
        # OpenAI's current parameter; compatible servers still expect max_tokens.
        body["max_completion_tokens" if self.kind == "openai" else "max_tokens"] = req.max_tokens
        if req.stop:
            body["stop"] = req.stop
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        return body

    @staticmethod
    def _usage(payload: dict[str, Any] | None) -> TokenUsage:
        usage = (payload or {}).get("usage") or {}
        return TokenUsage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )

    async def _post(self, body: dict[str, Any], model: str) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self._base}/chat/completions", headers=self._headers(), json=body
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, self.kind) from exc
        raise_for_status(response, model=model)
        result: dict[str, Any] = parse_json(response)
        return result

    @staticmethod
    def _text(data: dict[str, Any]) -> tuple[str, str | None]:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise ProviderRefusal(str(message["refusal"])[:300])
        return message.get("content") or "", choice.get("finish_reason")

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        started = time.monotonic()
        data = await self._post(self._body(req), req.model)
        text, finish = self._text(data)
        return GenerateResult(
            text=text,
            usage=self._usage(data),
            model=data.get("model", req.model),
            finish_reason=finish,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        usage = TokenUsage()
        try:
            async with self._client.stream(
                "POST",
                f"{self._base}/chat/completions",
                headers=self._headers(),
                json=self._body(req, stream=True),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status(response, model=req.model)
                async for _event, raw in iter_sse(response):
                    if raw.strip() == "[DONE]":
                        break
                    payload = loads_or_raise(raw)
                    if payload.get("usage"):
                        usage = self._usage(payload)
                    for choice in payload.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            yield StreamChunk(kind="text", text=piece)
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, self.kind) from exc
        yield StreamChunk(kind="usage", usage=usage)
        yield StreamChunk(kind="done")

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        if self._structured_mode == "prompt":
            return await super()._structured_call(req, json_schema, name)
        started = time.monotonic()
        body = self._body(req)
        if self._structured_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name[:60], "schema": json_schema, "strict": False},
            }
        else:
            body["response_format"] = {"type": "json_object"}
        try:
            data = await self._post(body, req.model)
        except ProviderBadRequest as exc:
            if any(h in exc.message.lower() for h in _FORMAT_HINTS):
                # The server does not support this response_format: step down and retry once.
                self._structured_mode = "json_object" if self._structured_mode == "json_schema" else "prompt"
                return await self._structured_call(req, json_schema, name)
            raise
        text, finish = self._text(data)
        return GenerateResult(
            text=text,
            usage=self._usage(data),
            model=data.get("model", req.model),
            finish_reason=finish,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def available_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(f"{self._base}/models", headers=self._headers())
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, self.kind) from exc
        raise_for_status(response)
        body = parse_json(response)
        items = body.get("data", body) if isinstance(body, dict) else body
        if not isinstance(items, list):
            raise ProviderError("Unexpected /models response shape")
        return [
            ModelInfo(id=m["id"], provider_id=self.provider_id, local=self.kind == "lmstudio")
            for m in items
            if isinstance(m, dict) and "id" in m
        ]
