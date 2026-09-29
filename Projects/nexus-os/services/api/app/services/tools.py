"""ToolService: the tool catalogue, per-tool enable switches, and the tool-call history."""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.events.bus import EventBus
from app.events.types import EventType
from app.repositories.runtime_store import ToolCallStore, ToolRowStore
from app.schemas.runtime import ToolCallOut, ToolOut
from app.tools.registry import ToolRegistry


class ToolService:
    def __init__(
        self, rows: ToolRowStore, calls: ToolCallStore, registry: ToolRegistry, bus: EventBus
    ) -> None:
        self._rows = rows
        self._calls = calls
        self._registry = registry
        self._bus = bus

    async def list_tools(self) -> list[ToolOut]:
        return await self._rows.list_tools()

    async def set_enabled(self, name: str, enabled: bool) -> ToolOut:
        if self._registry.get(name) is None:
            raise NotFoundError(f"Tool {name} not found")
        await self._rows.set_enabled(name, enabled)
        await self._bus.emit(
            EventType.SETTINGS_UPDATED,
            actor="user",
            payload={"changed": [f"tool:{name}"], "enabled": enabled},
        )
        return next(t for t in await self._rows.list_tools() if t.name == name)

    async def list_calls(
        self,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ToolCallOut]:
        return await self._calls.list_calls(project_id=project_id, run_id=run_id, status=status, limit=limit)

    async def get_call(self, call_id: str) -> ToolCallOut:
        return await self._calls.get(call_id)
