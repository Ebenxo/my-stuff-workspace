"""Harness for objectives: a ScriptBook of per-agent replies behind the real gateway and orchestrator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from app.providers.scripted import ScriptBook, ScriptedProvider
from app.repositories.events import EventFilter
from app.schemas.orchestration import ObjectiveCreate, ObjectiveOut, TaskOut
from app.schemas.projects import ProjectCreate
from app.schemas.providers import ProviderCreate
from app.schemas.runtime import ApprovalDecision, ApprovalOut
from app.services.container import AppContainer
from tests.agent_helpers import call, finish

__all__ = ["OE", "call", "finish", "make_oe", "plan", "review", "verdict"]


def plan(
    tasks: list[dict[str, Any]], criteria: list[str] | None = None, complexity: str = "medium"
) -> dict[str, Any]:
    return {
        "summary": "Here is the plan",
        "action": {
            "type": "finish",
            "result": {
                "objective": "The objective",
                "tasks": [{"description": t.get("title", ""), **t} for t in tasks],
                "completion_criteria": criteria or ["The deliverable exists"],
                "complexity": complexity,
            },
        },
    }


def review(
    verdict_: str = "approve", issues: list[dict[str, Any]] | None = None, summary: str = "Reviewed"
) -> dict[str, Any]:
    return {
        "summary": "Review done",
        "action": {
            "type": "finish",
            "result": {"verdict": verdict_, "summary": summary, "issues": issues or []},
        },
    }


def verdict(
    v: str = "PASS",
    criteria: list[tuple[str, bool]] | None = None,
    missing: list[str] | None = None,
    summary: str = "Checked the deliverables",
) -> dict[str, Any]:
    crit = criteria if criteria is not None else [("The deliverable exists", v == "PASS")]
    return {
        "summary": "Verification done",
        "action": {
            "type": "finish",
            "result": {
                "verdict": v,
                "summary": summary,
                "criteria": [{"criterion": c, "met": m, "evidence": "checked the file"} for c, m in crit],
                "missing_requirements": missing or [],
            },
        },
    }


@dataclass
class OE:
    c: AppContainer
    project_id: str
    book: ScriptBook
    provider: ScriptedProvider

    async def create(
        self, text: str = "Write a comparison report", run_mode: str = "auto", **kw: Any
    ) -> ObjectiveOut:
        return await self.c.objective_service.create(
            ObjectiveCreate(project_id=self.project_id, text=text, run_mode=run_mode, **kw)  # type: ignore[arg-type]
        )

    async def wait(self, objective_id: str, timeout: float = 30) -> ObjectiveOut:  # noqa: ASYNC109
        return await self.c.objective_service.wait_for(objective_id, timeout)

    async def tasks(self, objective_id: str) -> dict[str, TaskOut]:
        return {t.key: t for t in await self.c.task_store.list_for_objective(objective_id)}

    async def events(self, objective_id: str, *types: str) -> list[Any]:
        found = await self.c.bus.query(EventFilter(objective_id=objective_id), limit=1000)
        return [e for e in found if not types or e.type in types]

    async def event_types(self, objective_id: str) -> list[str]:
        return [e.type for e in await self.events(objective_id)]

    def requests_for(self, agent_name: str) -> list[str]:
        """Everything each model call of an agent was shown (system prompt + messages), in order."""
        out = []
        for r in self.provider.requests:
            if (r.system or "").startswith(f"You are the {agent_name} agent."):
                out.append((r.system or "") + "\n" + "\n".join(m.content for m in r.messages))
        return out

    async def pending(self, wait_s: float = 10.0) -> ApprovalOut:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while loop.time() < deadline:
            found = await self.c.approvals.list_approvals(status="PENDING", project_id=self.project_id)
            if found:
                return found[0]
            await asyncio.sleep(0.02)
        raise AssertionError("no approval was requested")

    async def decide(self, approval: ApprovalOut, decision: str) -> None:
        await self.c.approvals.decide(approval.id, ApprovalDecision(decision=decision))  # type: ignore[arg-type]

    async def task_status(self, objective_id: str, key: str, want: str, wait_s: float = 10.0) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        status = ""
        while loop.time() < deadline:
            task = (await self.tasks(objective_id)).get(key)
            status = task.status.value if task else ""
            if status == want:
                return status
            await asyncio.sleep(0.02)
        return status


async def make_oe(app: FastAPI, name: str = "Objective Tests") -> OE:
    c: AppContainer = app.state.container
    scripted: dict[str, ScriptedProvider] = {}

    async def no_sleep(_s: float) -> None:
        return None

    c.registry._demo_factory = lambda pid: scripted.setdefault(pid, ScriptedProvider(pid))  # type: ignore[attr-defined]
    c.gateway._sleep = no_sleep  # type: ignore[attr-defined]
    row = await c.providers.create(ProviderCreate(kind="demo", name="Demo", default_model="demo:scripted"))
    provider = scripted.setdefault(row.id, ScriptedProvider(row.id))
    book = ScriptBook()
    provider.fallback = book
    project = await c.projects.create(ProjectCreate(name=name))
    return OE(c=c, project_id=project.id, book=book, provider=provider)
