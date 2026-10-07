from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.runtime import ToolCallOut, ToolOut, ToolToggle

router = APIRouter(prefix="/api", tags=["tools"])


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(c: Container) -> list[ToolOut]:
    return await c.tool_service.list_tools()


@router.patch("/tools/{name}", response_model=ToolOut)
async def toggle_tool(name: str, body: ToolToggle, c: Container) -> ToolOut:
    return await c.tool_service.set_enabled(name, body.enabled)


@router.get("/tool-calls", response_model=list[ToolCallOut])
async def list_tool_calls(
    c: Container,
    project_id: str | None = None,
    run_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 100,
) -> list[ToolCallOut]:
    return await c.tool_service.list_calls(
        project_id=project_id, run_id=run_id, status=status_filter, limit=min(max(limit, 1), 300)
    )


@router.get("/tool-calls/{call_id}", response_model=ToolCallOut)
async def get_tool_call(call_id: str, c: Container) -> ToolCallOut:
    return await c.tool_service.get_call(call_id)
