"""MCP server configuration and status. Secret values are write-only: requests carry them, responses
only ever name them."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.risk import RiskLevel
from app.schemas.common import StrictModel

MCPTransport = Literal["stdio", "http"]
MCPStatus = Literal["stopped", "starting", "running", "error"]

SERVER_NAME = r"^[a-z0-9][a-z0-9-]{0,39}$"
ENV_NAME = r"^[A-Za-z_][A-Za-z0-9_]{0,59}$"
HEADER_NAME = r"^[A-Za-z0-9][A-Za-z0-9-]{0,59}$"


class MCPServerConfig(BaseModel):
    """What is stored in ``integrations.config``: everything except secret values."""

    transport: MCPTransport
    description: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    secret_env: list[str] = Field(default_factory=list)  # names; values are in the secret store
    secret_headers: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.HIGH
    timeout_s: float = 60.0


class MCPServerCreate(StrictModel):
    name: str = Field(pattern=SERVER_NAME)
    description: str = Field(default="", max_length=500)
    transport: MCPTransport
    command: str = Field(default="", max_length=1000)
    args: list[str] = Field(default_factory=list, max_length=50)
    cwd: str | None = Field(default=None, max_length=1000)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = Field(default="", max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    secret_env: dict[str, str] = Field(default_factory=dict)  # name → value (write-only)
    secret_headers: dict[str, str] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.HIGH
    timeout_s: float = Field(default=60.0, ge=1, le=600)
    enabled: bool = True


class MCPServerUpdate(StrictModel):
    description: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=1000)
    args: list[str] | None = Field(default=None, max_length=50)
    cwd: str | None = Field(default=None, max_length=1000)
    env: dict[str, str] | None = None
    url: str | None = Field(default=None, max_length=2000)
    headers: dict[str, str] | None = None
    # A value sets that secret, null removes it; names not mentioned keep their current value.
    secret_env: dict[str, str | None] | None = None
    secret_headers: dict[str, str | None] | None = None
    risk_level: RiskLevel | None = None
    timeout_s: float | None = Field(default=None, ge=1, le=600)
    enabled: bool | None = None


class MCPHealth(BaseModel):
    ok: bool
    checked_at: datetime
    latency_ms: float | None = None
    message: str = ""


class MCPServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    transport: MCPTransport
    command: str
    args: list[str]
    cwd: str | None
    env: dict[str, str]
    url: str
    headers: dict[str, str]
    secret_env: list[str]
    secret_headers: list[str]
    risk_level: RiskLevel
    timeout_s: float
    enabled: bool
    status: MCPStatus
    error: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None
    tools: int = 0
    resources: int = 0
    prompts: int = 0
    started_at: datetime | None = None
    last_health: MCPHealth | None = None
    created_at: datetime
    updated_at: datetime


class MCPToolOut(BaseModel):
    name: str  # as NEXUS knows it: mcp__<server>__<tool>
    original_name: str  # as the server knows it
    title: str = ""
    description: str
    input_schema: dict[str, Any]
    hints: list[str] = Field(default_factory=list)  # the server's own claims, shown as claims
    enabled: bool = True
    note: str | None = None  # why it was switched off (changed or suspicious definition)


class MCPResourceOut(BaseModel):
    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None


class MCPPromptArgument(BaseModel):
    name: str
    description: str = ""
    required: bool = False


class MCPPromptOut(BaseModel):
    name: str
    description: str = ""
    arguments: list[MCPPromptArgument] = Field(default_factory=list)


class MCPServerDetail(BaseModel):
    server: MCPServerOut
    instructions: str = ""
    tools: list[MCPToolOut] = Field(default_factory=list)
    resources: list[MCPResourceOut] = Field(default_factory=list)
    prompts: list[MCPPromptOut] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # tools NEXUS could not use, and why


class MCPLog(BaseModel):
    lines: list[str]


class ReadResource(StrictModel):
    uri: str = Field(min_length=1, max_length=2000)


class ResourceContent(BaseModel):
    uri: str
    mime_type: str | None = None
    text: str | None = None
    truncated: bool = False
    note: str | None = None


class GetPrompt(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    arguments: dict[str, str] = Field(default_factory=dict)


class PromptMessage(BaseModel):
    role: str
    text: str


class IntegrationRecord(BaseModel):
    """A stored integration row (repository DTO)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    name: str
    config: dict[str, Any]
    enabled: bool
    last_error: str | None = None
    last_health: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
