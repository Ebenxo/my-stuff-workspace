from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from app.api.deps import Container
from app.providers.router import ModelRouter, RouteRequest, TaskClass
from app.schemas.providers import Budgets, RoutePreview, RoutePreviewRequest, RoutingRules, UsageSummary

router = APIRouter(prefix="/api", tags=["usage"])


@router.get("/usage/summary", response_model=UsageSummary)
async def usage_summary(
    c: Container,
    days: int = 30,
    group_by: Literal["model", "provider", "agent", "project", "day", "purpose"] = "model",
) -> UsageSummary:
    return await c.usage.summary(days=min(max(days, 1), 365), group_by=group_by)


@router.get("/budgets", response_model=Budgets)
async def get_budgets(c: Container) -> Budgets:
    return await c.settings_service.get_budgets()


@router.put("/budgets", response_model=Budgets)
async def put_budgets(body: Budgets, c: Container) -> Budgets:
    return await c.settings_service.set_budgets(body)


@router.get("/routing/rules", response_model=RoutingRules)
async def get_rules(c: Container) -> RoutingRules:
    return await c.settings_service.get_routing_rules()


@router.put("/routing/rules", response_model=RoutingRules)
async def put_rules(body: RoutingRules, c: Container) -> RoutingRules:
    return await c.settings_service.set_routing_rules(body)


@router.post("/routing/preview", response_model=RoutePreview)
async def preview_route(body: RoutePreviewRequest, c: Container) -> RoutePreview:
    """What would the router pick for this kind of task? Never calls a model."""
    router_: ModelRouter = c.router
    route = await router_.route(
        RouteRequest(
            task_class=TaskClass(body.task_class),
            private=body.private,
            input_tokens=body.input_tokens,
            preferred=body.preferred_model,
            fallbacks=body.fallback_models,
        )
    )
    return RoutePreview(
        primary=str(route.primary), fallbacks=[str(f) for f in route.fallbacks], reason=route.reason
    )
