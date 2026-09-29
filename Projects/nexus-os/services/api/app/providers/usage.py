"""Usage recording, cost estimation and budget enforcement."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.clock import Clock
from app.core.ids import new_id
from app.events.bus import EventBus
from app.events.types import EventType
from app.models.database import Database
from app.models.foundation import UsageRecord
from app.providers.catalog import cost_usd
from app.providers.types import ModelInfo, TokenUsage
from app.repositories.providers import UsageRepository
from app.schemas.providers import Budgets, UsageGroup, UsageSummary

log = logging.getLogger(__name__)

BudgetsProvider = Callable[[], Awaitable[Budgets]]


@dataclass
class BudgetVerdict:
    allowed: bool = True
    warnings: list[str] = field(default_factory=list)
    exceeded: list[str] = field(default_factory=list)
    expensive: bool = False
    estimated_cost_usd: float | None = None


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class UsageService:
    def __init__(self, db: Database, bus: EventBus, clock: Clock, budgets: BudgetsProvider) -> None:
        self._db = db
        self._bus = bus
        self._clock = clock
        self._budgets = budgets
        self._warned: set[tuple[str, str]] = set()  # (scope, period) already warned about

    async def record(
        self,
        *,
        provider_id: str | None,
        model: str,
        usage: TokenUsage,
        latency_ms: int,
        info: ModelInfo | None,
        purpose: str = "agent",
        agent_id: str | None = None,
        project_id: str | None = None,
        objective_id: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
    ) -> UsageRecord:
        cost = cost_usd(usage.input_tokens, usage.output_tokens, info)
        async with self._db.session() as session:
            row = await UsageRepository(session).add(
                UsageRecord(
                    id=new_id("use"),
                    provider_id=provider_id,
                    model=model,
                    agent_id=agent_id,
                    project_id=project_id,
                    objective_id=objective_id,
                    workflow_id=workflow_id,
                    run_id=run_id,
                    purpose=purpose,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cost_usd=cost,
                    cost_known=cost is not None,
                    latency_ms=latency_ms,
                    created_at=self._clock.now(),
                )
            )
        await self._bus.emit(
            EventType.USAGE_RECORDED,
            project_id=project_id,
            objective_id=objective_id,
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "model": model,
                "provider_id": provider_id,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": cost,
                "estimated_tokens": usage.estimated,
            },
        )
        return row

    @staticmethod
    def estimate_cost(input_tokens: int, output_tokens: int, info: ModelInfo | None) -> float | None:
        return cost_usd(input_tokens, output_tokens, info)

    async def check_budget(
        self,
        *,
        est_input_tokens: int,
        est_output_tokens: int,
        info: ModelInfo | None,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> BudgetVerdict:
        """Would this call breach a limit? Warns at ``warn_at_fraction``; blocks at 100% if hard_stop."""
        b = await self._budgets()
        est_tokens = est_input_tokens + est_output_tokens
        est_cost = cost_usd(est_input_tokens, est_output_tokens, info)
        verdict = BudgetVerdict(estimated_cost_usd=est_cost)
        now = self._clock.now()
        if b.expensive_call_usd is not None and est_cost is not None and est_cost > b.expensive_call_usd:
            verdict.expensive = True

        checks: list[tuple[str, str, float | None, float | None, float | None, float | None]] = []
        # (scope label, period, usd limit, spent usd, token limit, spent tokens)
        async with self._db.session() as session:
            repo = UsageRepository(session)
            d_cost, d_tokens = await repo.totals_since(day_start(now))
            m_cost, m_tokens = await repo.totals_since(month_start(now))
            checks.append(("daily", "day", b.daily_usd, d_cost, b.daily_tokens, d_tokens))
            checks.append(("monthly", "month", b.monthly_usd, m_cost, b.monthly_tokens, m_tokens))
            if project_id and project_id in b.per_project_monthly_usd:
                pc, pt = await repo.totals_since(month_start(now), project_id=project_id)
                checks.append(
                    (f"project {project_id}", "month", b.per_project_monthly_usd[project_id], pc, None, pt)
                )
            if agent_id and agent_id in b.per_agent_monthly_usd:
                ac, at = await repo.totals_since(month_start(now), agent_id=agent_id)
                checks.append((f"agent {agent_id}", "month", b.per_agent_monthly_usd[agent_id], ac, None, at))

        period_key = {"day": day_start(now).date().isoformat(), "month": month_start(now).strftime("%Y-%m")}
        for scope, period, usd_limit, spent_usd, tok_limit, spent_tok in checks:
            projected_usd = (spent_usd or 0.0) + (est_cost or 0.0)
            projected_tok = (spent_tok or 0) + est_tokens
            for label, limit, projected in (
                ("USD", usd_limit, projected_usd),
                ("tokens", tok_limit, float(projected_tok)),
            ):
                if limit is None:
                    continue
                if projected > limit:
                    verdict.exceeded.append(f"{scope} {label} budget ({limit:g}) would be exceeded")
                elif limit > 0 and projected >= limit * b.warn_at_fraction:
                    key = (f"{scope}:{label}", period_key[period])
                    if key not in self._warned:
                        self._warned.add(key)
                        verdict.warnings.append(
                            f"{scope} {label} budget is {projected / limit:.0%} used "
                            f"({projected:g} of {limit:g})"
                        )

        if verdict.exceeded and b.hard_stop:
            verdict.allowed = False
        for text in verdict.warnings:
            await self._bus.emit(
                EventType.BUDGET_WARNING, project_id=project_id, agent_id=agent_id, payload={"message": text}
            )
        for text in verdict.exceeded:
            await self._bus.emit(
                EventType.BUDGET_EXCEEDED,
                project_id=project_id,
                agent_id=agent_id,
                payload={"message": text, "blocked": verdict.allowed is False},
            )
        return verdict

    async def summary(self, *, days: int, group_by: str) -> UsageSummary:
        since = self._clock.now() - timedelta(days=days)
        async with self._db.session() as session:
            groups = await UsageRepository(session).aggregate(since, group_by)
        return UsageSummary(
            days=days,
            group_by=group_by,
            groups=[
                UsageGroup(
                    key=g.key,
                    calls=g.calls,
                    input_tokens=g.input_tokens,
                    output_tokens=g.output_tokens,
                    cost_usd=round(g.cost_usd, 6),
                    unknown_cost_calls=g.unknown_cost_calls,
                )
                for g in groups
            ],
            total_calls=sum(g.calls for g in groups),
            total_tokens=sum(g.input_tokens + g.output_tokens for g in groups),
            total_cost_usd=round(sum(g.cost_usd for g in groups), 6),
            unknown_cost_calls=sum(g.unknown_cost_calls for g in groups),
        )
