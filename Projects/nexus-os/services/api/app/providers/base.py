"""LLMProvider: the one interface every model backend implements."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.security import redact_text
from app.providers.errors import (
    InvalidStructuredOutput,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.providers.jsonutil import describe_validation_error, extract_json
from app.providers.types import (
    ChatMessage,
    ConnectionTest,
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    StructuredResult,
    TokenUsage,
    estimate_request_tokens,
)

T = TypeVar("T", bound=BaseModel)

JSON_INSTRUCTION = (
    "Respond with exactly one JSON object that conforms to the JSON Schema below. "
    "Output only the JSON object: no prose, no code fences.\n\nJSON Schema:\n{schema}"
)


class LLMProvider(ABC):
    """Contract: generate, stream, generate_structured, count_tokens, available_models."""

    kind: str = "unknown"

    def __init__(self, provider_id: str, client: httpx.AsyncClient) -> None:
        self.provider_id = provider_id
        self._client = client

    # ---- required ----------------------------------------------------------------------
    @abstractmethod
    async def generate(self, req: GenerateRequest) -> GenerateResult: ...

    @abstractmethod
    def stream(self, req: GenerateRequest) -> AsyncIterator[StreamChunk]: ...

    @abstractmethod
    async def available_models(self) -> list[ModelInfo]: ...

    # ---- overridable -------------------------------------------------------------------
    async def count_tokens(self, req: GenerateRequest) -> int:
        """Token count for the request. Providers with a counting endpoint override this."""
        return estimate_request_tokens(req)

    async def _structured_call(
        self, req: GenerateRequest, json_schema: dict[str, Any], name: str
    ) -> GenerateResult:
        """One model call whose reply should be JSON. Default: schema in the prompt.

        Adapters override this to use the provider's native structured-output feature.
        """
        instruction = JSON_INSTRUCTION.format(schema=json.dumps(json_schema, separators=(",", ":")))
        system = f"{req.system}\n\n{instruction}" if req.system else instruction
        return await self.generate(req.model_copy(update={"system": system}))

    # ---- shared ------------------------------------------------------------------------
    async def generate_structured(
        self, req: GenerateRequest, schema: type[T], *, max_repairs: int = 2
    ) -> StructuredResult[T]:
        """Validated structured output with a bounded validate-and-repair loop."""
        json_schema = schema.model_json_schema()
        usage = TokenUsage()
        messages = list(req.messages)
        started = time.monotonic()
        last_reason = "unknown"
        for attempt in range(max_repairs + 1):
            result = await self._structured_call(
                req.model_copy(update={"messages": messages}), json_schema, schema.__name__
            )
            usage = usage + result.usage
            try:
                value = schema.model_validate(extract_json(result.text))
            except (ValueError, ValidationError) as exc:
                last_reason = describe_validation_error(exc)
                messages = [
                    *req.messages,
                    ChatMessage(role="assistant", content=result.text[:4000]),
                    ChatMessage(
                        role="user",
                        content=(
                            f"That reply could not be used: {last_reason}\n"
                            "Reply again with only the corrected JSON object."
                        ),
                    ),
                ]
                continue
            return StructuredResult[T](
                value=value,
                text=result.text,
                usage=usage,
                model=result.model,
                attempts=attempt + 1,
                repaired=attempt > 0,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        raise InvalidStructuredOutput(
            f"The model did not return valid {schema.__name__} after {max_repairs + 1} attempts: "
            f"{last_reason}",
            usage=usage,
        )

    async def test_connection(self) -> ConnectionTest:
        started = time.monotonic()
        try:
            models = await self.available_models()
        except ProviderError as exc:
            return ConnectionTest(
                ok=False,
                latency_ms=int((time.monotonic() - started) * 1000),
                detail=exc.message,
                error_code=exc.code,
            )
        return ConnectionTest(
            ok=True,
            latency_ms=int((time.monotonic() - started) * 1000),
            detail=f"Connected. {len(models)} model(s) available."
            if models
            else "Connected, no models listed.",
            models_found=len(models),
        )


# ---- HTTP helpers shared by adapters -----------------------------------------------------


def parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def error_message(response: httpx.Response) -> str:
    """Best-effort upstream message, redacted and length-limited. Never includes request headers."""
    try:
        body = response.json()
    except (ValueError, httpx.ResponseNotRead):
        return redact_text(response.text[:300]) or f"HTTP {response.status_code}"
    candidates: list[Any] = []
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            candidates = [err.get("message"), err.get("error"), err.get("detail")]
        else:
            candidates = [err, body.get("message"), body.get("detail")]
    for c in candidates:
        if isinstance(c, str) and c:
            return redact_text(c[:400])
    return f"HTTP {response.status_code}"


def parse_json(response: httpx.Response) -> Any:
    """JSON body, or a clear ProviderError (a captive portal or wrong URL often answers 200 with HTML)."""
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderBadRequest(
            "The endpoint did not return JSON. Check the base URL points at the API, not a web page."
        ) from exc


def loads_or_raise(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ProviderError("The provider sent malformed streaming data.") from exc


def raise_for_status(response: httpx.Response, *, model: str | None = None) -> None:
    status = response.status_code
    if 300 <= status < 400:
        # Redirects are never followed (an API-key header must not be replayed to another host).
        raise ProviderBadRequest(
            "The endpoint responded with a redirect, which is not followed for security. "
            "Update the base URL to the final address.",
            status=status,
        )
    if status < 400:
        return
    message = error_message(response)
    retry_after = parse_retry_after(response)
    if status in (401, 403):
        raise ProviderAuthError(f"Authentication failed: {message}", status=status)
    if status == 404 and model:
        raise ProviderModelNotFound(f"Model or endpoint not found ({model}): {message}", status=status)
    if status == 408:
        raise ProviderTimeout(message, status=status, retry_after=retry_after)
    if status == 429:
        raise ProviderRateLimited(message, status=status, retry_after=retry_after)
    if status >= 500 or status == 529:
        raise ProviderUnavailable(
            f"Provider error ({status}): {message}", status=status, retry_after=retry_after
        )
    raise ProviderBadRequest(message, status=status)


def wrap_transport_error(exc: Exception, target: str) -> ProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return ProviderTimeout(f"Timed out talking to {target}")
    if isinstance(exc, httpx.ConnectError):
        return ProviderUnavailable(f"Could not connect to {target}. Is it running and reachable?")
    return ProviderUnavailable(f"Network error talking to {target}: {type(exc).__name__}")
