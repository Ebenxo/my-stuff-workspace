"""Provider, usage, routing and budget contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import StrictModel

ProviderKindLiteral = Literal[
    "anthropic", "openai", "gemini", "ollama", "lmstudio", "openai_compatible", "demo"
]
Tier = Literal["fast", "balanced", "strong"]
TaskClassLiteral = Literal["formatting", "coding", "planning", "long_document", "general"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ModelPrice(StrictModel):
    """USD per million tokens. Set by the user; unknown prices stay unset (never guessed)."""

    input: float = Field(ge=0)
    output: float = Field(ge=0)


class ModelOverride(StrictModel):
    context_length: int | None = Field(default=None, ge=1)
    tier: Tier | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    price: ModelPrice | None = None


class ProviderOptions(StrictModel):
    models: dict[str, ModelOverride] = Field(default_factory=dict)
    structured_mode: Literal["json_schema", "json_object", "prompt"] = "json_schema"


class ProviderCreate(StrictModel):
    kind: ProviderKindLiteral
    name: Name
    base_url: str | None = Field(default=None, max_length=500)
    default_model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    options: ProviderOptions = Field(default_factory=ProviderOptions)
    enabled: bool = True


class ProviderUpdate(StrictModel):
    name: Name | None = None
    base_url: str | None = Field(default=None, max_length=500)
    default_model: str | None = Field(default=None, max_length=200)
    # None = leave the stored key alone; "" = remove it; anything else = replace it.
    api_key: str | None = Field(default=None, max_length=500, repr=False)
    options: ProviderOptions | None = None
    enabled: bool | None = None


class ProviderOut(BaseModel):
    """Never contains the key. ``has_key``/``key_hint`` let the UI show that one is stored."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: ProviderKindLiteral
    name: str
    base_url: str | None
    default_model: str | None
    enabled: bool
    options: ProviderOptions
    has_key: bool
    key_hint: str | None
    is_local: bool
    last_test_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None
    created_at: datetime


class ProviderKindInfo(BaseModel):
    kind: ProviderKindLiteral
    label: str
    default_base_url: str | None
    needs_key: bool
    local: bool
    help: str


class ModelOut(BaseModel):
    ref: str  # "<provider_id>:<model_id>"
    provider_id: str
    provider_name: str
    id: str
    display_name: str | None
    context_length: int | None
    tier: Tier | None
    local: bool
    input_cost_per_mtok: float | None
    output_cost_per_mtok: float | None


class ConnectionTestOut(BaseModel):
    ok: bool
    latency_ms: int
    detail: str
    models_found: int | None = None
    error_code: str | None = None


class UsageGroup(BaseModel):
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    unknown_cost_calls: int


class UsageSummary(BaseModel):
    days: int
    group_by: str
    groups: list[UsageGroup]
    total_calls: int
    total_tokens: int
    total_cost_usd: float
    unknown_cost_calls: int


class Budgets(StrictModel):
    """Limits are optional. Cost limits count only calls whose price is known; token limits count all."""

    daily_usd: float | None = Field(default=None, ge=0)
    monthly_usd: float | None = Field(default=None, ge=0)
    daily_tokens: int | None = Field(default=None, ge=0)
    monthly_tokens: int | None = Field(default=None, ge=0)
    per_project_monthly_usd: dict[str, float] = Field(default_factory=dict)
    per_agent_monthly_usd: dict[str, float] = Field(default_factory=dict)
    warn_at_fraction: float = Field(default=0.8, gt=0, le=1)
    hard_stop: bool = True
    expensive_call_usd: float | None = Field(default=0.5, ge=0)


class RoutingWhen(StrictModel):
    task_class: TaskClassLiteral | None = None
    private: bool | None = None
    min_input_tokens: int | None = Field(default=None, ge=1)


class RoutingPrefer(StrictModel):
    model: str | None = Field(default=None, max_length=300)  # "<provider_id>:<model>"
    provider_id: str | None = None
    tier: Tier | None = None
    local: bool | None = None


class RoutingRule(StrictModel):
    name: Name
    when: RoutingWhen = Field(default_factory=RoutingWhen)
    prefer: RoutingPrefer


class RoutingRules(StrictModel):
    rules: list[RoutingRule] = Field(default_factory=list, max_length=50)


class RoutePreviewRequest(StrictModel):
    task_class: TaskClassLiteral = "general"
    private: bool = False
    input_tokens: int = Field(default=0, ge=0)
    preferred_model: str | None = None
    fallback_models: list[str] = Field(default_factory=list)


class RoutePreview(BaseModel):
    primary: str
    fallbacks: list[str]
    reason: str
