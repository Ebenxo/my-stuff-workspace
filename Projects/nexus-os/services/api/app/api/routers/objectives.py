from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import Container
from app.schemas.orchestration import (
    ObjectiveCreate,
    ObjectiveDetail,
    ObjectiveOut,
    ObjectiveRun,
    PlanEdit,
    TaskAnswer,
    TaskOut,
)

router = APIRouter(prefix="/api", tags=["objectives"])


@router.post("/objectives", response_model=ObjectiveOut, status_code=status.HTTP_202_ACCEPTED)
async def create_objective(body: ObjectiveCreate, c: Container) -> ObjectiveOut:
    """Accept an objective and start planning it in the background."""
    return await c.objective_service.create(body)


@router.get("/objectives", response_model=list[ObjectiveOut])
async def list_objectives(
    c: Container, project_id: str | None = None, status_filter: str | None = None, limit: int = 50
) -> list[ObjectiveOut]:
    return await c.objective_service.list_objectives(
        project_id=project_id, status=status_filter, limit=min(max(limit, 1), 200)
    )


@router.get("/objectives/{objective_id}", response_model=ObjectiveDetail)
async def get_objective(objective_id: str, c: Container) -> ObjectiveDetail:
    return await c.objective_service.detail(objective_id)


@router.put("/objectives/{objective_id}/plan", response_model=ObjectiveDetail)
async def edit_plan(objective_id: str, body: PlanEdit, c: Container) -> ObjectiveDetail:
    return await c.objective_service.edit_plan(objective_id, body)


@router.post(
    "/objectives/{objective_id}/run", response_model=ObjectiveOut, status_code=status.HTTP_202_ACCEPTED
)
async def run_objective(objective_id: str, body: ObjectiveRun, c: Container) -> ObjectiveOut:
    return await c.objective_service.run(objective_id, body)


@router.post("/objectives/{objective_id}/cancel", response_model=ObjectiveOut)
async def cancel_objective(objective_id: str, c: Container) -> ObjectiveOut:
    return await c.objective_service.cancel(objective_id)


@router.post(
    "/objectives/{objective_id}/resume", response_model=ObjectiveOut, status_code=status.HTTP_202_ACCEPTED
)
async def resume_objective(objective_id: str, c: Container) -> ObjectiveOut:
    return await c.objective_service.resume(objective_id)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, c: Container) -> TaskOut:
    return await c.objective_service.get_task(task_id)


@router.post("/tasks/{task_id}/retry", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED)
async def retry_task(task_id: str, c: Container) -> TaskOut:
    return await c.objective_service.retry_task(task_id)


@router.post("/tasks/{task_id}/skip", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED)
async def skip_task(task_id: str, c: Container) -> TaskOut:
    return await c.objective_service.skip_task(task_id)


@router.post("/tasks/{task_id}/answer", response_model=TaskOut, status_code=status.HTTP_202_ACCEPTED)
async def answer_task(task_id: str, body: TaskAnswer, c: Container) -> TaskOut:
    return await c.objective_service.answer_task(task_id, body.text)
