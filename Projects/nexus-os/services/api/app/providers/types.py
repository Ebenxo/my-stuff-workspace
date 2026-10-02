"""Provider-neutral request/response types."""

from __future__ import annotations

import math
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

ReasoningMode = Literal["off", "light", "deep"]
ProviderKind = Literal["anthropic", "openai", "gemini", "ollama", "lmstudio", "openai_compatible", "demo"]

T = TypeVar("T", bound=BaseModel)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GenerateRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    system: str | None = None
    temperature: float | None = 0.2
    max_tokens: int = Field(default=4096, ge=1)
    # Controls provider-side thinking budgets only. Thinking output is discarded, never stored.
    reasoning: ReasoningMode = "off"
    stop: list[str] | None = None


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            estimated=self.estimated or other.estimated,
        )

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class GenerateResult(BaseModel):
    text: str
    usage: TokenUsage
    model: str
    finish_reason: str | None = None
    latency_ms: int = 0


class StreamChunk(BaseModel):
    kind: Literal["text", "usage", "done"]
    text: str = ""
    usage: TokenUsage | None = None


class StructuredResult(BaseModel, Generic[T]):
    value: T
    text: str
    usage: TokenUsage
    model: str
    attempts: int = 1
    repaired: bool = False
    latency_ms: int = 0


class ModelInfo(BaseModel):
    id: str
    provider_id: str
    display_name: str | None = None
    context_length: int | None = None
    supports_vision: bool | None = None
    supports_tools: bool | None = None
    supports_reasoning: bool | None = None
    tier: Literal["fast", "balanced", "strong"] | None = None
    input_cost_per_mtok: float | None = None
    output_cost_per_mtok: float | None = None
    local: bool = False


class ConnectionTest(BaseModel):
    ok: bool
    latency_ms: int
    detail: str
    models_found: int | None = None
    error_code: str | None = None


def estimate_tokens(text: str) -> int:
    """Conservative token estimate (about 3.5 characters per token). Used where no counter exists."""
    return math.ceil(len(text) / 3.5) if text else 0


def estimate_request_tokens(req: GenerateRequest) -> int:
    total = estimate_tokens(req.system or "")
    for m in req.messages:
        total += estimate_tokens(m.content) + 4
    return total
