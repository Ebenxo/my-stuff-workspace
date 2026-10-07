"""LLMGateway: the one doorway from agents to models.

route -> budget check -> call with bounded retries -> fall back to other models -> record usage.
Agents never touch a provider adapter directly, so routing, budgets, privacy and accounting cannot
be bypassed.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.failures import FailureCategory
from app.events.bus import EventBus
from app.events.types import EventType
from app.providers.base import LLMProvider
from app.providers.errors import (
    BudgetExceededError,
    InvalidStructuredOutput,
    NoRouteError,
    ProviderError,
    ProviderRefusal,
    ProviderTimeout,
)
from app.providers.registry import ProviderRegistry
from app.providers.router import ModelRef, ModelRouter, RouteRequest, TaskClass
from app.providers.types import (
    GenerateRequest,
    GenerateResult,
    ModelInfo,
    StreamChunk,
    StructuredResult,
    TokenUsage,
    estimate_request_tokens,
    estimate_tokens,
)
from app.providers.usage import UsageService

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
EST_OUTPUT_TOKENS = 1000  # heuristic for budget projection before the call is made


@dataclass(frozen=True)
class CallContext:
    purpose: str = "agent"
    agent_id: str | None = None
    project_id: str | None = None
    objective_id: str | None = None
    workflow_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    task_class: TaskClass = TaskClass.GENERAL
    private: bool = False
    preferred_model: str | None = None
    fallback_models: tuple[str, ...] = ()
    manual_override: str | None = None
    max_retries: int = 2  # retries per model for retryable errors


@dataclass
class Attempt:
    model: str
    error_code: str
    message: str


@dataclass
class CallMeta:
    model: str = ""
    provider_id: str = ""
    route_reason: str = ""
    fallback_used: bool = False
    retries: int = 0
    attempts: list[Attempt] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


class GatewayError(Exception):
    """Every model in the route failed (or the call was refused/blocked)."""

    def __init__(
        self, category: FailureCategory, message: str, *, code: str, attempts: list[Attempt]
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.code = code
        self.attempts = attempts


def categorize(exc: BaseException) -> FailureCategory:
    if isinstance(exc, InvalidStructuredOutput):
        return FailureCategory.INVALID_OUTPUT
    if isinstance(exc, ProviderTimeout):
        return FailureCategory.TIMEOUT
    return FailureCategory.MODEL_FAILURE


Invoke = Callable[[LLMProvider, GenerateRequest], Awaitable[tuple[Any, TokenUsage, int]]]


class LLMGateway:
    def __init__(
        self,
        registry: ProviderRegistry,
        router: ModelRouter,
        usage: UsageService,
        bus: EventBus,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        backoff_base_s: float = 1.0,
        backoff_cap_s: float = 30.0,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._registry = registry
        self._router = router
        self._usage = usage
        self._bus = bus
        self._sleep = sleep
        self._backoff_base = backoff_base_s
        self._backoff_cap = backoff_cap_s
        self._jitter = jitter

    # ---- public API --------------------------------------------------------------------
    async def generate(self, ctx: CallContext, req: GenerateRequest) -> tuple[GenerateResult, CallMeta]:
        async def invoke(p: LLMProvider, r: GenerateRequest) -> tuple[GenerateResult, TokenUsage, int]:
            out = await p.generate(r)
            return out, out.usage, out.latency_ms

        result, meta = await self._run(ctx, req, invoke)
        return result, meta

    async def generate_structured(
        self, ctx: CallContext, req: GenerateRequest, schema: type[T], *, max_repairs: int = 2
    ) -> tuple[StructuredResult[T], CallMeta]:
        async def invoke(p: LLMProvider, r: GenerateRequest) -> tuple[StructuredResult[T], TokenUsage, int]:
            out = await p.generate_structured(r, schema, max_repairs=max_repairs)
            return out, out.usage, out.latency_ms

        result, meta = await self._run(ctx, req, invoke)
        return result, meta

    async def count_tokens(self, ctx: CallContext, req: GenerateRequest) -> int:
        route = await self._route(ctx, estimate_request_tokens(req))
        provider = await self._registry.get_provider(route.primary.provider_id)
        return await provider.count_tokens(req.model_copy(update={"model": route.primary.model}))

    async def stream(self, ctx: CallContext, req: GenerateRequest) -> AsyncIterator[StreamChunk]:
        """Stream from the routed model. Fallback happens only before the first chunk is sent."""
        est_in = estimate_request_tokens(req)
        route = await self._route(ctx, est_in)
        meta = CallMeta(route_reason=route.reason)
        refs = [route.primary, *route.fallbacks]
        for idx, ref in enumerate(refs):
            info = await self._registry.model_info(ref.provider_id, ref.model)
            await self._enforce_budget(ctx, est_in, req, info, meta)
            provider = await self._registry.get_provider(ref.provider_id)
            started_output = False
            text_parts: list[str] = []
            usage: TokenUsage | None = None
            try:
                async for chunk in provider.stream(req.model_copy(update={"model": ref.model})):
                    if chunk.kind == "text":
                        started_output = True
                        text_parts.append(chunk.text)
                    elif chunk.kind == "usage":
                        usage = chunk.usage
                        continue  # usage is recorded, not forwarded
                    yield chunk
            except ProviderError as exc:
                meta.attempts.append(Attempt(str(ref), exc.code, exc.message))
                if (
                    started_output
                    or isinstance(exc, ProviderRefusal | BudgetExceededError)
                    or idx == len(refs) - 1
                ):
                    raise GatewayError(
                        categorize(exc), exc.message, code=exc.code, attempts=meta.attempts
                    ) from exc
                await self._note_fallback(ctx, ref, refs[idx + 1], exc)
                continue
            final = (
                usage
                if usage and usage.total
                else TokenUsage(
                    input_tokens=est_in, output_tokens=estimate_tokens("".join(text_parts)), estimated=True
                )
            )
            await self._record(ctx, ref, info, final, 0)
            return

    # ---- internals ---------------------------------------------------------------------
    async def _route(self, ctx: CallContext, est_in: int) -> Any:
        try:
            return await self._router.route(
                RouteRequest(
                    task_class=ctx.task_class,
                    private=ctx.private,
                    input_tokens=est_in,
                    preferred=ctx.preferred_model,
                    fallbacks=list(ctx.fallback_models),
                    manual_override=ctx.manual_override,
                )
            )
        except NoRouteError as exc:
            raise GatewayError(
                FailureCategory.MODEL_FAILURE, exc.message, code=exc.code, attempts=[]
            ) from exc

    async def _enforce_budget(
        self, ctx: CallContext, est_in: int, req: GenerateRequest, info: ModelInfo, meta: CallMeta
    ) -> None:
        verdict = await self._usage.check_budget(
            est_input_tokens=est_in,
            est_output_tokens=min(req.max_tokens, EST_OUTPUT_TOKENS),
            info=info,
            project_id=ctx.project_id,
            agent_id=ctx.agent_id,
        )
        if verdict.expensive:
            await self._bus.emit(
                EventType.BUDGET_WARNING,
                project_id=ctx.project_id,
                run_id=ctx.run_id,
                payload={
                    "message": f"This call is estimated at ${verdict.estimated_cost_usd:.2f}",
                    "expensive": True,
                },
            )
        if not verdict.allowed:
            message = "; ".join(verdict.exceeded)
            meta.attempts.append(Attempt(f"{info.provider_id}:{info.id}", BudgetExceededError.code, message))
            raise GatewayError(
                FailureCategory.MODEL_FAILURE,
                f"Budget limit reached: {message}",
                code=BudgetExceededError.code,
                attempts=meta.attempts,
            )

    async def _record(
        self, ctx: CallContext, ref: ModelRef, info: ModelInfo, usage: TokenUsage, latency_ms: int
    ) -> None:
        await self._usage.record(
            provider_id=ref.provider_id,
            model=ref.model,
            usage=usage,
            latency_ms=latency_ms,
            info=info,
            purpose=ctx.purpose,
            agent_id=ctx.agent_id,
            project_id=ctx.project_id,
            objective_id=ctx.objective_id,
            workflow_id=ctx.workflow_id,
            run_id=ctx.run_id,
        )

    async def _note_fallback(
        self, ctx: CallContext, failed: ModelRef, nxt: ModelRef, exc: ProviderError
    ) -> None:
        await self._bus.emit(
            EventType.RECOVERY_DECISION,
            project_id=ctx.project_id,
            objective_id=ctx.objective_id,
            run_id=ctx.run_id,
            agent_id=ctx.agent_id,
            payload={
                "action": "change_model",
                "from": str(failed),
                "to": str(nxt),
                "reason": exc.code,
                "detail": exc.message[:200],
            },
        )

    def _delay(self, attempt: int, exc: ProviderError) -> float:
        base = min(self._backoff_cap, self._backoff_base * (2**attempt))
        wait = max(exc.retry_after or 0.0, base) + self._jitter() * 0.25 * base
        return float(min(wait, self._backoff_cap))

    async def _run(self, ctx: CallContext, req: GenerateRequest, invoke: Invoke) -> tuple[Any, CallMeta]:
        est_in = estimate_request_tokens(req)
        route = await self._route(ctx, est_in)
        meta = CallMeta(route_reason=route.reason)
        refs = [route.primary, *route.fallbacks]
        last: ProviderError | None = None

        for idx, ref in enumerate(refs):
            info = await self._registry.model_info(ref.provider_id, ref.model)
            await self._enforce_budget(ctx, est_in, req, info, meta)
            provider = await self._registry.get_provider(ref.provider_id)
            attempt = 0
            while True:
                try:
                    result, usage, latency = await invoke(
                        provider, req.model_copy(update={"model": ref.model})
                    )
                except InvalidStructuredOutput as exc:
                    if isinstance(exc.usage, TokenUsage):
                        await self._record(ctx, ref, info, exc.usage, 0)
                    meta.attempts.append(Attempt(str(ref), exc.code, exc.message))
                    last = exc
                    break
                except ProviderRefusal as exc:
                    # A refusal is the model's answer, not an outage: never shop for a more compliant model.
                    meta.attempts.append(Attempt(str(ref), exc.code, exc.message))
                    raise GatewayError(
                        FailureCategory.MODEL_FAILURE, exc.message, code=exc.code, attempts=meta.attempts
                    ) from exc
                except ProviderError as exc:
                    meta.attempts.append(Attempt(str(ref), exc.code, exc.message))
                    last = exc
                    if exc.retryable and attempt < ctx.max_retries:
                        meta.retries += 1
                        await self._sleep(self._delay(attempt, exc))
                        attempt += 1
                        continue
                    break
                else:
                    await self._record(ctx, ref, info, usage, latency)
                    meta.model, meta.provider_id = ref.model, ref.provider_id
                    meta.fallback_used = idx > 0
                    meta.usage = usage
                    return result, meta
            if idx + 1 < len(refs) and last is not None:
                await self._note_fallback(ctx, ref, refs[idx + 1], last)

        assert last is not None
        raise GatewayError(categorize(last), last.message, code=last.code, attempts=meta.attempts) from last
