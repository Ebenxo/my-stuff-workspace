"""Test harness for agent runs: a scripted model behind the real gateway, router, runner and executor."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from app.agents.runner import RunOutcome, RunRequest
from app.core.risk import RiskLevel
from app.providers.scripted import ScriptedProvider
from app.repositories.events import EventFilter
from app.schemas.agents import (
    AgentDefinition,
    AgentStep,
    AskHumanAction,
    FinishAction,
    TaskResult,
    ToolCallAction,
)
from app.schemas.common import PermissionLevel
from app.schemas.projects import ProjectCreate
from app.schemas.providers import ProviderCreate
from app.schemas.runtime import ApprovalDecision, ApprovalOut
from app.services.container import AppContainer
from tests.runtime_helpers import make_agent


def call(tool: str, args: dict[str, Any] | None = None, summary: str = "Working on it") -> AgentStep:
    return AgentStep(
        summary=summary, action=ToolCallAction(type="tool_call", tool=tool, arguments=args or {})
    )


def finish(summary: str = "All done", status: str = "completed", **kw: Any) -> AgentStep:
    return AgentStep(
        summary="Finishing",
        action=FinishAction(type="finish", result=TaskResult(status=status, summary=summary, **kw)),  # type: ignore[arg-type]
    )


def ask(question: str, options: list[str] | None = None) -> AgentStep:
    return AgentStep(
        summary="I need an answer",
        action=AskHumanAction(type="ask_human", question=question, options=options or []),
    )


@dataclass
class AE:
    c: AppContainer
    project_id: str
    provider: ScriptedProvider
    sleeps: list[float]
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    def spawn(self, coro: Any) -> asyncio.Task[Any]:
        """Start a background run that the fixture will cancel if the test leaves it parked."""
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    async def cleanup(self) -> None:
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 10)

    def agent(self, **kw: Any) -> AgentDefinition:
        limits = {k: kw.pop(k) for k in list(kw) if k in AgentDefinition.model_fields}
        tools = kw.pop("tools", None)
        base = make_agent(tools=tools, max_risk=kw.pop("max_risk", RiskLevel.HIGH), **kw)
        return base.model_copy(update=limits)

    def request(self, agent: AgentDefinition, prompt: str = "Do the task", **kw: Any) -> RunRequest:
        kw.setdefault("permission_level", PermissionLevel.BALANCED)
        return RunRequest(agent=agent, project_id=self.project_id, prompt=prompt, **kw)

    async def run(self, agent: AgentDefinition, prompt: str = "Do the task", **kw: Any) -> RunOutcome:
        return await asyncio.wait_for(self.c.runner.run(self.request(agent, prompt, **kw)), 20)

    async def events(self, *types: str, run_id: str | None = None) -> list[Any]:
        found = await self.c.bus.query(EventFilter(project_id=self.project_id), limit=500)
        return [e for e in found if (not types or e.type in types) and (run_id is None or e.run_id == run_id)]

    async def pending(self, wait_s: float = 5.0) -> ApprovalOut:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while loop.time() < deadline:
            found = await self.c.approvals.list_approvals(status="PENDING", project_id=self.project_id)
            if found:
                return found[0]
            await asyncio.sleep(0.02)
        raise AssertionError("no approval was requested")

    async def status_of(self, run_id: str, want: str, wait_s: float = 5.0) -> str:
        """Run status is eventually consistent with its approval (the approval row is written first)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        status = ""
        while loop.time() < deadline:
            status = (await self.c.run_store.get(run_id)).status.value
            if status == want:
                return status
            await asyncio.sleep(0.02)
        return status

    async def decide(self, approval: ApprovalOut, decision: str, **kw: Any) -> ApprovalOut:
        return await self.c.approvals.decide(approval.id, ApprovalDecision(decision=decision, **kw))  # type: ignore[arg-type]

    async def step_messages(self, index: int = -1) -> str:
        """Everything the model was shown on one call (system prompt included)."""
        req = self.provider.requests[index]
        return (req.system or "") + "\n" + "\n".join(m.content for m in req.messages)


async def make_ae(app: FastAPI, name: str = "Agent Tests") -> AE:
    c: AppContainer = app.state.container
    scripted: dict[str, ScriptedProvider] = {}
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    c.registry._demo_factory = lambda pid: scripted.setdefault(pid, ScriptedProvider(pid))  # type: ignore[attr-defined]
    c.gateway._sleep = fake_sleep  # type: ignore[attr-defined]
    c.router.auto_route_demo = True  # these tests drive agents with scripted models
    provider_row = await c.providers.create(
        ProviderCreate(kind="demo", name="Demo", default_model="demo:scripted")
    )
    provider = scripted.setdefault(provider_row.id, ScriptedProvider(provider_row.id))
    project = await c.projects.create(ProjectCreate(name=name))
    return AE(c=c, project_id=project.id, provider=provider, sleeps=sleeps)
