"""Tool interface. A tool is data plus a handler; it can only be *run* by the ToolExecutor, which
is where validation, policy, approval, sandboxing and logging happen."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.risk import RiskLevel
from app.files.artifacts import ArtifactStore
from app.files.fs import WorkspaceFS
from app.permissions.policy import RiskAssessment


class Capability(StrEnum):
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_DELETE = "fs.delete"
    PROC_EXEC = "proc.exec"
    CODE_EXEC = "code.exec"
    NET_HTTP = "net.http"
    NET_SEARCH = "net.search"
    DB_READ = "db.read"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    ARTIFACT_WRITE = "artifact.write"
    UI_CLIPBOARD = "ui.clipboard"
    MCP = "mcp"


class ToolError(Exception):
    """A tool failed in an expected way. The message is shown to the agent (and user)."""

    code = "tool_error"

    def __init__(self, message: str, *, code: str | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.retryable = retryable


EmitFn = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class ToolContext:
    """Exactly what a handler may use. No database session, no secrets, no process environment."""

    project_id: str | None
    run_id: str | None
    task_id: str | None
    objective_id: str | None
    agent_id: str | None
    fs: WorkspaceFS
    project_dir: Path
    sandbox: Any  # SandboxManager
    http: Any  # SafeHttpClient
    artifacts: ArtifactStore
    emit: EmitFn
    search: Any = None  # SearchService
    memory: Any = None  # MemoryFacade (Phase 7)
    allowed_domains: list[str] = field(default_factory=list)
    unattended: bool = False


Handler = Callable[[ToolContext, Any], Awaitable[Any]]
Assessor = Callable[[ToolContext, Any], RiskAssessment]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: type[BaseModel]
    risk_level: RiskLevel
    handler: Handler
    output_schema: type[BaseModel] | None = None
    requires_approval: bool = False  # always ask, at every permission level
    permissions: frozenset[Capability] = frozenset()
    assess_risk: Assessor | None = None
    describe_impact: Callable[[Any], str] | None = None
    returns_untrusted: bool = False  # the result is external content: fence it and taint the run
    source_label: Callable[[Any], str] | None = None
    alternatives: tuple[str, ...] = ()  # tools the recovery planner may try instead
    timeout_s: float = 30.0
    max_output_chars: int = 20_000
    source: str = "builtin"

    def json_schema(self) -> dict[str, Any]:
        return self.input_schema.model_json_schema()

    def signature(self) -> str:
        """One line for the prompt: name(arg: type, ...) - description."""
        props = self.json_schema().get("properties", {})
        required = set(self.json_schema().get("required", []))
        parts = []
        for name, spec in props.items():
            t = spec.get("type") or ("|".join(a.get("type", "any") for a in spec.get("anyOf", [])) or "any")
            parts.append(f"{name}{'' if name in required else '?'}: {t}")
        return f"{self.name}({', '.join(parts)})"
