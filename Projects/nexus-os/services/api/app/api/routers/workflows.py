from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Container
from app.schemas.common import StrictModel
from app.schemas.workflows import (
    CronPreview,
    NodeDecision,
    RunWorkflow,
    ScheduleCreate,
    ScheduleOut,
    ScheduleUpdate,
    ValidationReport,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowOut,
    WorkflowRunDetail,
    WorkflowRunOut,
    WorkflowUpdate,
    WorkflowVersionOut,
)

router = APIRouter(prefix="/api", tags=["workflows"])


class ValidateBody(StrictModel):
    project_id: str
    definition: WorkflowDefinition
    workflow_id: str | None = None


class AnswerBody(StrictModel):
    text: str


# ---- workflows ----------------------------------------------------------------------------------


@router.get("/workflows", response_model=list[WorkflowOut])
async def list_workflows(c: Container, project_id: str | None = None) -> list[WorkflowOut]:
    return await c.workflows.list_workflows(project_id)


@router.post("/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(body: WorkflowCreate, c: Container) -> WorkflowOut:
    return await c.workflows.create(body)


@router.post("/workflows/validate", response_model=ValidationReport)
async def validate_workflow(body: ValidateBody, c: Container) -> ValidationReport:
    """Check a definition without saving it (the editor calls this as you work)."""
    return await c.workflows.validate(body.definition, project_id=body.project_id, self_id=body.workflow_id)


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: str, c: Container) -> WorkflowOut:
    return await c.workflows.get(workflow_id)


@router.put("/workflows/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(workflow_id: str, body: WorkflowUpdate, c: Container) -> WorkflowOut:
    """Save changes. A changed graph becomes a new version; runs keep the version they started with."""
    return await c.workflows.update(workflow_id, body)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: str, c: Container) -> Response:
    await c.workflows.delete(workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workflows/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
async def workflow_versions(workflow_id: str, c: Container) -> list[WorkflowVersionOut]:
    return await c.workflows.versions(workflow_id)


@router.post(
    "/workflows/{workflow_id}/run", response_model=WorkflowRunOut, status_code=status.HTTP_202_ACCEPTED
)
async def run_workflow(workflow_id: str, body: RunWorkflow, c: Container) -> WorkflowRunOut:
    return await c.workflows.start(workflow_id, body.inputs)


@router.get("/workflows/{workflow_id}/runs", response_model=list[WorkflowRunOut])
async def workflow_runs(workflow_id: str, c: Container, limit: int = 30) -> list[WorkflowRunOut]:
    return await c.workflows.list_runs(workflow_id=workflow_id, limit=min(max(limit, 1), 200))


# ---- runs ---------------------------------------------------------------------------------------


@router.get("/workflow-runs", response_model=list[WorkflowRunOut])
async def list_workflow_runs(
    c: Container, project_id: str | None = None, limit: int = 30
) -> list[WorkflowRunOut]:
    return await c.workflows.list_runs(project_id=project_id, limit=min(max(limit, 1), 200))


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunDetail)
async def get_workflow_run(run_id: str, c: Container) -> WorkflowRunDetail:
    return await c.workflows.detail(run_id)


@router.post("/workflow-runs/{run_id}/cancel", response_model=WorkflowRunOut)
async def cancel_workflow_run(run_id: str, c: Container) -> WorkflowRunOut:
    return await c.workflows.cancel(run_id)


@router.post("/workflow-runs/{run_id}/retry", response_model=WorkflowRunOut)
async def retry_workflow_run(run_id: str, c: Container) -> WorkflowRunOut:
    """Run the failed steps again (and whatever was waiting on them)."""
    return await c.workflows.retry(run_id)


@router.post("/workflow-runs/{run_id}/nodes/{node_id}/approve", response_model=WorkflowRunOut)
async def approve_node(run_id: str, node_id: str, body: NodeDecision, c: Container) -> WorkflowRunOut:
    return await c.workflows.decide(run_id, node_id, approved=True, note=body.note)


@router.post("/workflow-runs/{run_id}/nodes/{node_id}/reject", response_model=WorkflowRunOut)
async def reject_node(run_id: str, node_id: str, body: NodeDecision, c: Container) -> WorkflowRunOut:
    return await c.workflows.decide(run_id, node_id, approved=False, note=body.note)


@router.post("/workflow-runs/{run_id}/nodes/{node_id}/answer", response_model=WorkflowRunOut)
async def answer_node(run_id: str, node_id: str, body: AnswerBody, c: Container) -> WorkflowRunOut:
    return await c.workflows.answer(run_id, node_id, body.text)


# ---- schedules ----------------------------------------------------------------------------------


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(c: Container, workflow_id: str | None = None) -> list[ScheduleOut]:
    return await c.scheduler.list_schedules(workflow_id)


@router.get("/schedules/preview", response_model=CronPreview)
async def preview_schedule(c: Container, cron: str, timezone: str = "UTC") -> CronPreview:
    """Describe a cron expression and show its next five times (422 if it is not valid)."""
    return c.scheduler.preview(cron, timezone)


@router.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(body: ScheduleCreate, c: Container) -> ScheduleOut:
    return await c.scheduler.create(body)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(schedule_id: str, body: ScheduleUpdate, c: Container) -> ScheduleOut:
    return await c.scheduler.update(schedule_id, body)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, c: Container) -> Response:
    await c.scheduler.delete(schedule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/schedules/{schedule_id}/run-now", response_model=ScheduleOut)
async def run_schedule_now(schedule_id: str, c: Container) -> ScheduleOut:
    return await c.scheduler.run_now(schedule_id)
