from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Container
from app.core.errors import NotFoundError
from app.schemas.runtime import ApprovalDecision, ApprovalOut, SessionGrantOut

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    c: Container,
    status_filter: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    limit: int = 100,
) -> list[ApprovalOut]:
    return await c.approvals.list_approvals(
        status=status_filter, project_id=project_id, run_id=run_id, limit=min(max(limit, 1), 300)
    )


@router.get("/grants", response_model=list[SessionGrantOut])
async def list_grants(c: Container) -> list[SessionGrantOut]:
    return [
        SessionGrantOut(id=g.id, project_id=g.project_id, tool_name=g.tool_name, created_at=g.created_at)
        for g in c.approvals.grants.list_grants()
    ]


@router.delete("/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_grant(grant_id: str, c: Container) -> Response:
    if not c.approvals.grants.revoke(grant_id):
        raise NotFoundError("That grant no longer exists.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(approval_id: str, c: Container) -> ApprovalOut:
    return await c.approvals.get(approval_id)


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide(approval_id: str, body: ApprovalDecision, c: Container) -> ApprovalOut:
    return await c.approvals.decide(approval_id, body)
