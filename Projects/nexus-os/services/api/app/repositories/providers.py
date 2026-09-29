"""Provider configuration and usage persistence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.foundation import ProviderConfiguration, UsageRecord


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, provider_id: str) -> ProviderConfiguration | None:
        return await self.session.get(ProviderConfiguration, provider_id)

    async def list_all(self, *, enabled_only: bool = False) -> Sequence[ProviderConfiguration]:
        stmt = select(ProviderConfiguration).order_by(ProviderConfiguration.created_at.asc())
        if enabled_only:
            stmt = stmt.where(ProviderConfiguration.enabled.is_(True))
        return (await self.session.execute(stmt)).scalars().all()

    async def add(self, row: ProviderConfiguration) -> ProviderConfiguration:
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete(self, row: ProviderConfiguration) -> None:
        await self.session.delete(row)
        await self.session.flush()


@dataclass(frozen=True)
class UsageAggregate:
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    unknown_cost_calls: int


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: UsageRecord) -> UsageRecord:
        self.session.add(row)
        await self.session.flush()
        return row

    async def totals_since(
        self,
        since: datetime,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
    ) -> tuple[float, int]:
        """(known cost in USD, total tokens) since ``since``, optionally scoped."""
        stmt = select(
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
            func.coalesce(func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0),
        ).where(UsageRecord.created_at >= since)
        if project_id is not None:
            stmt = stmt.where(UsageRecord.project_id == project_id)
        if agent_id is not None:
            stmt = stmt.where(UsageRecord.agent_id == agent_id)
        cost, tokens = (await self.session.execute(stmt)).one()
        return float(cost or 0.0), int(tokens or 0)

    async def aggregate(self, since: datetime, group_by: str) -> list[UsageAggregate]:
        columns = {
            "model": UsageRecord.model,
            "provider": UsageRecord.provider_id,
            "agent": UsageRecord.agent_id,
            "project": UsageRecord.project_id,
            "day": func.date(UsageRecord.created_at),
            "purpose": UsageRecord.purpose,
        }
        if group_by not in columns:
            raise ValueError(f"unsupported group_by: {group_by}")
        col = columns[group_by]
        stmt = (
            select(
                col,
                func.count(),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
                func.coalesce(func.sum(case((UsageRecord.cost_known.is_(False), 1), else_=0)), 0),
            )
            .where(UsageRecord.created_at >= since)
            .group_by(col)
            .order_by(col)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            UsageAggregate(
                key=str(k) if k is not None else "(none)",
                calls=int(calls),
                input_tokens=int(i),
                output_tokens=int(o),
                cost_usd=float(c or 0.0),
                unknown_cost_calls=int(u or 0),
            )
            for k, calls, i, o, c, u in rows
        ]

    async def recent(self, limit: int = 100) -> Sequence[UsageRecord]:
        stmt = select(UsageRecord).order_by(UsageRecord.id.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()
