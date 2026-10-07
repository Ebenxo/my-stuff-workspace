"""Google Gemini REST adapter. The API key is sent in a header, never in the URL."""

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

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider(LLMProvider):
    kind = "gemini"

    def __init__(
        self, provider_id: str, client: httpx.AsyncClient, *, api_key: str | None, base_url: str | None = None
    ) -> None:
        super().__init__(provider_id, client)
        self._key = api_key
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._native_schema = True

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._key:
            headers["x-goog-api-key"] = self._key
        return headers

    @staticmethod
    def _model_path(model: str) -> str:
        return model if model.startswith("models/") else f"models/{model}"

    def _body(self, req: GenerateRequest, extra_config: dict[str, Any] | None = None) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": req.max_tokens}
        if req.temperature is not None:
            config["temperature"] = req.temperature
        if req.stop:
            config["stopSequences"] = req.stop
        config.update(extra_config or {})
        body: dict[str, Any] = {
            "contents": [
                {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
                for m in req.messages
            ],
            "generationConfig": config,
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        return body

    @staticmethod
    def _usage(data: dict[str, Any]) -> TokenUsage:
        meta = data.get("usageMetadata") or {}
        return TokenUsage(
            input_tokens=int(meta.get("promptTokenCount") or 0),
            output_tokens=int(meta.get("candidatesTokenCount") or 0),
        )

    @staticmethod
    def _text(data: dict[str, Any]) -> tuple[str, str | None]:
        feedback = data.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise ProviderRefusal(f"Request blocked by the provider: {feedback['blockReason']}")
        candidates = data.get("candidates") or []
        if not candidates:
            return "", None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        # Parts flagged as thoughts are discarded.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return text, candidates[0].get("finishReason")

    async def _call(self, req: GenerateRequest, extra_config: dict[str, Any] | None = None) -> GenerateResult:
        started = time.monotonic()
        url = f"{self._base}/v1beta/{self._model_path(req.model)}:generateContent"
        try:
            response = await self._client.post(
                url, headers=self._headers(), json=self._body(req, extra_config)
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Gemini") from exc
        raise_for_status(response, model=req.model)
        data = parse_json(response)
        text, finish = self._text(data)
        return GenerateResult(
            text=text,
            usage=self._usage(data),
            model=req.model,
            finish_reason=finish,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def generate(self, req: GenerateRequest) -> GenerateResult:
        return await self._call(req)

    async def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        usage = TokenUsage()
        url = f"{self._base}/v1beta/{self._model_path(req.model)}:streamGenerateContent"
        try:
            async with self._client.stream(
                "POST", url, headers=self._headers(), params={"alt": "sse"}, json=self._body(req)
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_status(response, model=req.model)
                async for _event, raw in iter_sse(response):
                    payload = loads_or_raise(raw)
                    text, _ = self._text(payload)
                    if text:
                        yield StreamChunk(kind="text", text=text)
                    if payload.get("usageMetadata"):
                        usage = self._usage(payload)
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Gemini") from exc
        yield StreamChunk(kind="usage", usage=usage)
        yield StreamChunk(kind="done")

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        if not self._native_schema:
            return await super()._structured_call(req, json_schema, name)
        try:
            return await self._call(
                req, {"responseMimeType": "application/json", "responseJsonSchema": json_schema}
            )
        except ProviderBadRequest as exc:
            if "schema" in exc.message.lower() or "response" in exc.message.lower():
                # This model/API version rejects native schemas: use schema-in-prompt from now on.
                self._native_schema = False
                return await super()._structured_call(req, json_schema, name)
            raise

    async def count_tokens(self, req: GenerateRequest) -> int:
        url = f"{self._base}/v1beta/{self._model_path(req.model)}:countTokens"
        try:
            response = await self._client.post(
                url,
                headers=self._headers(),
                json={"generateContentRequest": {"model": self._model_path(req.model), **self._body(req)}},
            )
            raise_for_status(response, model=req.model)
            return int(parse_json(response).get("totalTokens", 0))
        except (httpx.HTTPError, ProviderError):
            return await super().count_tokens(req)

    async def available_models(self) -> list[ModelInfo]:
        try:
            response = await self._client.get(
                f"{self._base}/v1beta/models", headers=self._headers(), params={"pageSize": 100}
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, "Gemini") from exc
        raise_for_status(response)
        out: list[ModelInfo] = []
        for m in parse_json(response).get("models", []):
            if "generateContent" not in m.get("supportedGenerationMethods", ["generateContent"]):
                continue
            out.append(
                ModelInfo(
                    id=str(m["name"]).removeprefix("models/"),
                    provider_id=self.provider_id,
                    display_name=m.get("displayName"),
                    context_length=m.get("inputTokenLimit"),
                )
            )
        return out
