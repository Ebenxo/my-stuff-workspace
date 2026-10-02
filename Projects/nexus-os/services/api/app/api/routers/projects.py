from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, status

from app.api.deps import Container
from app.schemas.projects import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    c: Container, status_filter: Literal["active", "archived"] | None = None
) -> list[ProjectOut]:
    return await c.projects.list_all(status=status_filter)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, c: Container) -> ProjectOut:
    return await c.projects.create(body)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, c: Container) -> ProjectOut:
    return await c.projects.get(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, body: ProjectUpdate, c: Container) -> ProjectOut:
    return await c.projects.update(project_id, body)


@router.post("/projects/{project_id}/archive", response_model=ProjectOut)
async def archive_project(project_id: str, c: Container) -> ProjectOut:
    return await c.projects.set_status(project_id, "archived")


@router.post("/projects/{project_id}/unarchive", response_model=ProjectOut)
async def unarchive_project(project_id: str, c: Container) -> ProjectOut:
    return await c.projects.set_status(project_id, "active")


@router.get("/projects/{project_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(project_id: str, c: Container) -> list[ConversationOut]:
    return await c.conversations.list_for_project(project_id)


@router.post(
    "/projects/{project_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(project_id: str, body: ConversationCreate, c: Container) -> ConversationOut:
    return await c.conversations.create(project_id, body)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str, c: Container, after_id: str | None = None, limit: int = 200
) -> list[MessageOut]:
    return await c.conversations.messages(conversation_id, after_id=after_id, limit=min(max(limit, 1), 500))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(conversation_id: str, body: MessageCreate, c: Container) -> MessageOut:
    return await c.conversations.add_message(conversation_id, role="user", content=body.content)
