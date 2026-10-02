from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import Container
from app.schemas.mcp import (
    GetPrompt,
    MCPLog,
    MCPServerCreate,
    MCPServerDetail,
    MCPServerOut,
    MCPServerUpdate,
    PromptMessage,
    ReadResource,
    ResourceContent,
)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/servers", response_model=list[MCPServerOut])
async def list_servers(c: Container) -> list[MCPServerOut]:
    return await c.mcp.list_servers()


@router.post("/servers", response_model=MCPServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(body: MCPServerCreate, c: Container) -> MCPServerOut:
    return await c.mcp.create(body)


@router.get("/servers/{server_id}", response_model=MCPServerDetail)
async def get_server(server_id: str, c: Container) -> MCPServerDetail:
    return await c.mcp.detail(server_id)


@router.patch("/servers/{server_id}", response_model=MCPServerOut)
async def update_server(server_id: str, body: MCPServerUpdate, c: Container) -> MCPServerOut:
    return await c.mcp.update(server_id, body)


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: str, c: Container) -> Response:
    await c.mcp.delete(server_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/servers/{server_id}/start", response_model=MCPServerOut)
async def start_server(server_id: str, c: Container) -> MCPServerOut:
    return await c.mcp.start(server_id)


@router.post("/servers/{server_id}/stop", response_model=MCPServerOut)
async def stop_server(server_id: str, c: Container) -> MCPServerOut:
    return await c.mcp.stop(server_id)


@router.post("/servers/{server_id}/check", response_model=MCPServerOut)
async def check_server(server_id: str, c: Container) -> MCPServerOut:
    return await c.mcp.check(server_id)


@router.get("/servers/{server_id}/log", response_model=MCPLog)
async def server_log(server_id: str, c: Container) -> MCPLog:
    return MCPLog(lines=await c.mcp.log(server_id))


@router.post("/servers/{server_id}/resources/read", response_model=list[ResourceContent])
async def read_resource(server_id: str, body: ReadResource, c: Container) -> list[ResourceContent]:
    return await c.mcp.read_resource(server_id, body.uri)


@router.post("/servers/{server_id}/prompts/get", response_model=list[PromptMessage])
async def get_prompt(server_id: str, body: GetPrompt, c: Container) -> list[PromptMessage]:
    return await c.mcp.get_prompt(server_id, body.name, body.arguments)
