"""Project, conversation, message and settings contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import PermissionLevel, StrictModel

Name120 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Title200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ProjectSettings(StrictModel):
    permission_level: PermissionLevel | None = None  # None = inherit the user default
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    allowed_domains: list[str] = Field(default_factory=list)
    linked_folders: list[str] = Field(default_factory=list)


class ProjectCreate(StrictModel):
    name: Name120
    description: str = Field(default="", max_length=2000)
    icon: str = Field(default="folder", max_length=40)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)


class ProjectUpdate(StrictModel):
    name: Name120 | None = None
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=40)
    settings: ProjectSettings | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str
    icon: str
    status: Literal["active", "archived"]
    is_demo: bool
    settings: ProjectSettings
    created_at: datetime
    updated_at: datetime


class ConversationCreate(StrictModel):
    title: Title200 = "New conversation"


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=100_000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: Literal["user", "assistant", "agent", "system"]
    agent_id: str | None
    content: str
    meta: dict[str, object]
    created_at: datetime


class UserSettingsUpdate(StrictModel):
    display_name: str | None = Field(default=None, max_length=120)
    workspace_root: str | None = Field(default=None, max_length=1000)
    default_permission_level: PermissionLevel | None = None
    onboarding_completed: bool | None = None
    preferences: dict[str, object] | None = None


class UserSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str
    workspace_root: str
    default_permission_level: PermissionLevel
    onboarding_completed: bool
    preferences: dict[str, object]
    updated_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: str
    body: str
    project_id: str | None
    ref: dict[str, object]
    read_at: datetime | None
    created_at: datetime
