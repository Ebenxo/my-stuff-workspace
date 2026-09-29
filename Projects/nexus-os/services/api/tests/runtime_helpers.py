"""Shared setup for tests that run tools or agents against the real container and database."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from app.core.ids import new_id
from app.core.risk import RiskLevel
from app.permissions.approvals import ApprovalService
from app.permissions.taint import TaintTracker
from app.schemas.agents import AgentDefinition, AgentPermissions
from app.schemas.common import PermissionLevel
from app.schemas.projects import ProjectCreate
from app.schemas.runtime import ApprovalDecision, ApprovalOut
from app.services.container import AppContainer
from app.tools.executor import ExecContext, ToolExecutor, ToolOutcome


@dataclass
class RT:
    c: AppContainer
    project_id: str
    agent: AgentDefinition
    level: PermissionLevel
    waits: list[str | None] = field(default_factory=list)

    @property
    def executor(self) -> ToolExecutor:
        return self.c.executor

    @property
    def approvals(self) -> ApprovalService:
        return self.c.approvals

    async def ectx(self, *, unattended: bool = False, taint: TaintTracker | None = None, level: PermissionLevel | None = None,
                   agent: AgentDefinition | None = None, ttl: float | None = 30) -> ExecContext:
        agent = agent or self.agent
        run_id = new_id("run")
        tctx = await self.c.tool_contexts.build(project_id=self.project_id, run_id=run_id, agent_id=agent.id, unattended=unattended)

        async def on_wait(a: ApprovalOut | None) -> None:
            self.waits.append(a.id if a else None)

        return ExecContext(project_id=self.project_id, run_id=run_id, task_id=None, objective_id=None, agent=agent,
                           permission_level=level or self.level, tool_context=tctx, taint=taint or TaintTracker(), unattended=unattended,
                           on_wait=on_wait, approval_ttl_s=ttl)

    async def call(self, name: str, args: dict[str, Any], ectx: ExecContext | None = None, summary: str = "test") -> ToolOutcome:
        return await self.executor.execute(ectx or await self.ectx(), name, args, summary=summary)

    async def pending(self, timeout: float = 5.0) -> ApprovalOut:
        """Wait for a run to park on an approval, and return it."""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            found = await self.approvals.list_approvals(status="PENDING", project_id=self.project_id)
            if found:
                return found[0]
            await asyncio.sleep(0.02)
        raise AssertionError("no approval was requested")

    async def decide(self, approval: ApprovalOut, decision: str, **kw: Any) -> ApprovalOut:
        return await self.approvals.decide(approval.id, ApprovalDecision(decision=decision, **kw))  # type: ignore[arg-type]

    def read(self, rel: str) -> str:
        return (self.c.projects_dir / rel).read_text()  # replaced in make_rt


ALL_TOOLS = ["*"]


def make_agent(*, tools: list[str] | None = None, max_risk: RiskLevel = RiskLevel.HIGH, may_ask: bool = True, slug: str = "tester") -> AgentDefinition:
    return AgentDefinition(id=new_id("agent"), slug=slug, name="Tester", role="Testing", tools=tools if tools is not None else ["*"],
                           permissions=AgentPermissions(max_risk=max_risk, may_request_approval=may_ask))


async def make_rt(app: FastAPI, *, level: PermissionLevel = PermissionLevel.BALANCED, tools: list[str] | None = None,
                  max_risk: RiskLevel = RiskLevel.HIGH, may_ask: bool = True, name: str = "Tool Tests") -> RT:
    c: AppContainer = app.state.container
    project = await c.projects.create(ProjectCreate(name=name))
    agent = make_agent(tools=tools, max_risk=max_risk, may_ask=may_ask)
    rt = RT(c=c, project_id=project.id, agent=agent, level=level)
    root = await c.projects.project_dir(project.id)

    class Files:
        projects_dir = root

    rt.c = c
    object.__setattr__(rt, "read", lambda rel: (root / rel).read_text())
    rt.root = root  # type: ignore[attr-defined]
    return rt
