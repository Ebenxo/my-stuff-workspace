"""Builds the narrow ToolContext a handler receives for one run."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.events.bus import EventBus
from app.events.types import EventType
from app.files.artifacts import ArtifactStore
from app.files.fs import WorkspaceFS
from app.tools.base import ToolContext
from app.tools.netguard import SafeHttpClient
from app.tools.sandbox import SandboxManager


class ToolContextFactory:
    def __init__(
        self,
        *,
        project_dir_for: Callable[[str], Awaitable[Path]],
        project_domains_for: Callable[[str], Awaitable[list[str]]],
        sandbox: SandboxManager,
        http: SafeHttpClient,
        artifacts: ArtifactStore,
        bus: EventBus,
        search: Any = None,
        memory: Any = None,
    ) -> None:
        self._dir = project_dir_for
        self._domains = project_domains_for
        self._sandbox = sandbox
        self._http = http
        self._artifacts = artifacts
        self._bus = bus
        self._search = search
        self._memory = memory

    def set_memory(self, memory: Any) -> None:
        self._memory = memory

    async def build(
        self,
        *,
        project_id: str,
        run_id: str | None,
        task_id: str | None = None,
        objective_id: str | None = None,
        agent_id: str | None = None,
        unattended: bool = False,
        private: bool = False,
        agent_slug: str | None = None,
        memory_read: tuple[str, ...] = (),
        memory_write: tuple[str, ...] = (),
    ) -> ToolContext:
        project_dir = await self._dir(project_id)

        async def emit(type_name: str, payload: dict[str, Any]) -> None:
            await self._bus.emit(
                EventType(type_name),
                project_id=project_id,
                objective_id=objective_id,
                task_id=task_id,
                run_id=run_id,
                agent_id=agent_id,
                payload=payload,
            )

        return ToolContext(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            objective_id=objective_id,
            agent_id=agent_id,
            fs=WorkspaceFS(project_dir),
            project_dir=project_dir,
            sandbox=self._sandbox,
            http=self._http,
            artifacts=self._artifacts,
            emit=emit,
            search=self._search,
            memory=self._memory,
            allowed_domains=await self._domains(project_id),
            unattended=unattended,
            private=private,
            agent_slug=agent_slug,
            memory_read=memory_read,
            memory_write=memory_write,
        )
