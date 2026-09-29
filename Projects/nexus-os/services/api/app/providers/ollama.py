"""Ollama native API adapter (local models)."""

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
from app.providers.sse import iter_ndjson
from app.providers.types import (
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    TokenUsage,
)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"


class OllamaProvider(LLMProvider):
    kind = "ollama"

    def __init__(
        self,
        provider_id: str,
        client: httpx.AsyncClient,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(provider_id, client)
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        return headers

    def _body(
        self, req: GenerateRequest, *, stream: bool, fmt: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend({"role": m.role, "content": m.content} for m in req.messages)
        options: dict[str, Any] = {"num_predict": req.max_tokens}
        if req.temperature is not None:
            options["temperature"] = req.temperature
        if req.stop:
            options["stop"] = req.stop
        body: dict[str, Any] = {
            "model": req.model,
            "messages": messages,
            "stream": stream,
            "options": options,
        }
        if fmt is not None:
            body["format"] = fmt
        return body

    @staticmethod
    def _usage(payload: dict[str, Any]) -> TokenUsage:
        return TokenUsage(
            input_tokens=int(payload.get("prompt_eval_count") or 0),
            output_tokens=int(payload.get("eval_count") or 0),
        )

    async def _chat(self, req: GenerateRequest, fmt: dict[str, Any] | None = None) -> GenerateResult:
        started = time.monotonic()
        try:
            response = await self._client.post(
                f"{self._base}/api/chat", headers=self._headers(), json=self._body(req, stream=False, fmt=fmt)
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Ollama") from exc
        raise_for_status(response, model=req.model)
        data = parse_json(response)
        return GenerateResult(
            text=(data.get("message") or {}).get("content", ""),
            usage=self._usage(data),
            model=data.get("model", req.model),
            finish_reason=data.get("done_reason"),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        return await self._chat(req)

    async def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        usage = TokenUsage()
        try:
            async with self._client.stream(
                "POST", f"{self._base}/api/chat", headers=self._headers(), json=self._body(req, stream=True)
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status(response, model=req.model)
                async for line in iter_ndjson(response):
                    payload = loads_or_raise(line)
                    piece = (payload.get("message") or {}).get("content")
                    if piece:
                        yield StreamChunk(kind="text", text=piece)
                    if payload.get("done"):
                        usage = self._usage(payload)
                        break
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Ollama") from exc
        yield StreamChunk(kind="usage", usage=usage)
        yield StreamChunk(kind="done")

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        # Ollama constrains decoding to the schema natively via `format`.
        return await self._chat(req, fmt=json_schema)

    async def available_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(f"{self._base}/api/tags", headers=self._headers())
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Ollama") from exc
        raise_for_status(response)
        return [
            ModelInfo(id=m["name"], provider_id=self.provider_id, local=True)
            for m in parse_json(response).get("models", [])
            if "name" in m
        ]
