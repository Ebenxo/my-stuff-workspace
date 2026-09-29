from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from app.api.deps import Container
from app.schemas.agents import AgentCreate, AgentDefinition, AgentUpdate
from app.schemas.common import StrictModel
from app.schemas.runtime import AgentRunOut, AgentRunRequest, ToolCallOut

router = APIRouter(prefix="/api", tags=["agents"])


class RunDetail(BaseModel):
    run: AgentRunOut
    steps: list[dict[str, Any]]
    tool_calls: list[ToolCallOut]


class AnswerBody(StrictModel):
    text: str = Field(min_length=1, max_length=10_000)


@router.get("/agents", response_model=list[AgentDefinition])
async def list_agents(c: Container) -> list[AgentDefinition]:
    return await c.agent_service.list_agents()


@router.post("/agents", response_model=AgentDefinition, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, c: Container) -> AgentDefinition:
    return await c.agent_service.create_agent(body)


@router.post("/agents/run", response_model=AgentRunOut, status_code=status.HTTP_202_ACCEPTED)
async def run_agent(body: AgentRunRequest, c: Container) -> AgentRunOut:
    return await c.agent_service.start_run(body)


@router.get("/agents/{agent_id}", response_model=AgentDefinition)
async def get_agent(agent_id: str, c: Container) -> AgentDefinition:
    return await c.agent_service.get_agent(agent_id)


@router.patch("/agents/{agent_id}", response_model=AgentDefinition)
async def update_agent(agent_id: str, body: AgentUpdate, c: Container) -> AgentDefinition:
    return await c.agent_service.update_agent(agent_id, body)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, c: Container) -> Response:
    await c.agent_service.delete_agent(agent_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    c: Container,
    project_id: str | None = None,
    agent: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[AgentRunOut]:
    return await c.agent_service.list_runs(
        project_id=project_id, agent_id=agent, status=status_filter, limit=min(max(limit, 1), 200)
    )


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, c: Container) -> RunDetail:
    run, steps, calls = await c.agent_service.run_detail(run_id)
    return RunDetail(run=run, steps=steps, tool_calls=calls)


@router.post("/runs/{run_id}/cancel", response_model=AgentRunOut)
async def cancel_run(run_id: str, c: Container) -> AgentRunOut:
    return await c.agent_service.cancel(run_id)


@router.post("/runs/{run_id}/resume", response_model=AgentRunOut, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: str, c: Container) -> AgentRunOut:
    return await c.agent_service.resume(run_id)


@router.post("/runs/{run_id}/answer", response_model=AgentRunOut, status_code=status.HTTP_202_ACCEPTED)
async def answer_run(run_id: str, body: AnswerBody, c: Container) -> AgentRunOut:
    return await c.agent_service.answer(run_id, body.text)
