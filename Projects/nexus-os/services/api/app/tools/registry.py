"""ToolRegistry: dynamic registration; every tool (built-in, MCP, skill) lives here."""

from __future__ import annotations

import re
from typing import Any

from app.tools.base import ToolDefinition

_NAME = re.compile(r"^(?:[a-z][a-z0-9_]{1,63}|mcp__[a-z0-9_-]{1,40}__[A-Za-z0-9_-]{1,60})$")


def matches(pattern: str, name: str) -> bool:
    """Agent allow-list entries are exact names or ``prefix*``."""
    if pattern.endswith("*"):
        return name.startswith(pattern[:-1])
    return pattern == name


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if not _NAME.match(tool.name):
            raise ValueError(f"invalid tool name {tool.name!r}")
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        tool.input_schema.model_json_schema()  # fail fast on a schema that cannot be described
        self._tools[tool.name] = tool

    def unregister_source(self, source: str) -> int:
        """Remove every tool from a source (e.g. an MCP server that stopped) atomically."""
        doomed = [n for n, t in self._tools.items() if t.source == source]
        for n in doomed:
            del self._tools[n]
        return len(doomed)

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda t: (t.source, t.name))

    def allowed_for(self, allow_list: list[str], *, disabled: set[str] | None = None) -> list[ToolDefinition]:
        """What an agent may use: on its allow-list, registered and not disabled by the user.
        This is also exactly what the model is shown, so it never sees a tool it cannot call."""
        off = disabled or set()
        return [t for t in self.all() if t.name not in off and any(matches(p, t.name) for p in allow_list)]

    def mirror_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "source": t.source,
                "description": t.description,
                "input_schema": t.json_schema(),
                "output_schema": t.output_schema.model_json_schema() if t.output_schema else None,
                "risk_level": t.risk_level.value,
                "requires_approval": t.requires_approval,
                "capabilities": sorted(c.value for c in t.permissions),
            }
            for t in self.all()
        ]
