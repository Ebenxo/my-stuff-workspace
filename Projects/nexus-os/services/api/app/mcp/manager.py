"""MCPServerManager: runs the MCP servers the person added and offers their tools to agents.

- Each server tool registers as ``mcp__<server>__<tool>`` at the server's risk level (HIGH unless the
  person chose otherwise). It runs only through the ToolExecutor, so allow-lists, policy, approvals,
  unattended rules and logging apply as to any tool. Its results are untrusted content (fenced, scanned,
  and they taint the run), and ``Capability.MCP`` keeps every MCP tool away from private runs.
- A tool's description and argument schema are the server's words: they are cleaned (invisible
  characters removed, lengths capped) and scanned for instructions aimed at the model. A suspicious tool
  is registered switched off, with the reason shown to the person.
- Definitions are fingerprinted. When a server changes a tool the person already had, the tool is
  switched off until they look at it again (a server cannot quietly swap what a tool says it does).
- Tool annotations (read-only, destructive, ...) are the server's claims: shown as hints, never used as
  permissions.
- A server that stops on its own is reported and its tools are withdrawn; nothing restarts it silently.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.clock import Clock, SystemClock
from app.core.risk import RiskLevel
from app.core.security import redact_text
from app.core.trust import scan_for_injection
from app.events.bus import EventBus
from app.events.types import EventType
from app.mcp.client import Handshake, MCPClient
from app.mcp.jsonschema import MAX_DESCRIPTION, MCPArguments, args_model, clean_schema, clean_text
from app.mcp.protocol import (
    METHOD_NOT_FOUND,
    MCPError,
    render_prompt,
    render_resource,
    render_tool_result,
)
from app.mcp.transport import HttpTransport, LogTail, StdioTransport, Transport, new_http_client
from app.repositories.runtime_store import ToolRowStore
from app.tools.base import Capability, ToolContext, ToolDefinition, ToolError
from app.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

MAX_TOOLS = 200
CONNECT_TIMEOUT_S = 30.0
LIST_TIMEOUT_S = 30.0


@dataclass
class ServerSpec:
    """Everything needed to start one server, secrets included (never stored or logged)."""

    id: str
    name: str
    transport: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.HIGH
    timeout_s: float = 60.0

    @property
    def source(self) -> str:
        return f"mcp:{self.name}"


@dataclass
class DiscoveredTool:
    name: str  # registered name
    original: str  # the server's name for it
    title: str
    description: str
    schema: dict[str, Any]
    hints: list[str]
    fingerprint: str
    flag: str | None


@dataclass
class LiveServer:
    spec: ServerSpec
    status: str = "stopped"  # stopped | starting | running | error
    error: str | None = None
    client: MCPClient | None = None
    handshake: Handshake | None = None
    tools: list[DiscoveredTool] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime | None = None
    log: LogTail = field(default_factory=LogTail)
    refresh_task: asyncio.Task[None] | None = None


def registered_name(server: str, original: str, taken: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]", "_", original)[:60].strip("_") or "tool"
    name, n = f"mcp__{server}__{base}", 2
    while name in taken:
        suffix = f"_{n}"
        name, n = f"mcp__{server}__{base[: 60 - len(suffix)]}{suffix}", n + 1
    taken.add(name)
    return name


def _hints(annotations: Any) -> list[str]:
    if not isinstance(annotations, dict):
        return []
    out = []
    if annotations.get("readOnlyHint") is True:
        out.append("The server says this tool only reads.")
    if annotations.get("destructiveHint") is True:
        out.append("The server says this tool may change or delete things.")
    if annotations.get("openWorldHint") is True:
        out.append("The server says this tool reaches outside services.")
    return out


def _schema_texts(schema: Any, depth: int = 0) -> list[str]:
    if depth > 12:
        return []
    if isinstance(schema, dict):
        texts = [v for k, v in schema.items() if k in ("description", "title") and isinstance(v, str)]
        for v in schema.values():
            texts += _schema_texts(v, depth + 1)
        return texts
    if isinstance(schema, list):
        return [t for item in schema for t in _schema_texts(item, depth + 1)]
    return []


def _fingerprint(raw: dict[str, Any]) -> str:
    shape = {k: raw.get(k) for k in ("name", "title", "description", "inputSchema", "outputSchema")}
    return hashlib.sha256(json.dumps(shape, sort_keys=True, default=str).encode()).hexdigest()


class MCPServerManager:
    def __init__(
        self,
        registry: ToolRegistry,
        tool_rows: ToolRowStore,
        bus: EventBus,
        clock: Clock | None = None,
        *,
        http_factory: Callable[[], httpx.AsyncClient] = new_http_client,
        connect_timeout: float = CONNECT_TIMEOUT_S,
    ) -> None:
        self._registry = registry
        self._rows = tool_rows
        self._bus = bus
        self._clock = clock or SystemClock()
        self._http_factory = http_factory
        self._connect_timeout = connect_timeout
        self._live: dict[str, LiveServer] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ---- state ---------------------------------------------------------------------------
    def live(self, server_id: str) -> LiveServer | None:
        return self._live.get(server_id)

    def _lock(self, server_id: str) -> asyncio.Lock:
        return self._locks.setdefault(server_id, asyncio.Lock())

    async def _emit(
        self, type_: EventType, live: LiveServer, payload: dict[str, Any], actor: str = "system"
    ) -> None:
        await self._bus.emit(
            type_, actor=actor, payload={"server_id": live.spec.id, "name": live.spec.name, **payload}
        )

    # ---- lifecycle -----------------------------------------------------------------------
    def _transport(self, spec: ServerSpec) -> Transport:
        if spec.transport == "http":
            return HttpTransport(spec.url, spec.headers, self._http_factory)
        return StdioTransport(spec.command, spec.args, spec.env, spec.cwd or Path.cwd())

    async def start(self, spec: ServerSpec, *, actor: str = "system") -> LiveServer:
        async with self._lock(spec.id):
            current = self._live.get(spec.id)
            if current is not None and current.status == "running":
                return current
            if current is not None:
                await self._teardown(current)
            live = LiveServer(spec=spec, status="starting")
            self._live[spec.id] = live
            transport = self._transport(spec)
            live.log = transport.log
            holder: list[MCPClient] = []  # callbacks name the client they belong to (stale ones are ignored)

            async def on_close(reason: str) -> None:
                await self._lost(spec.id, holder[0], reason)

            async def on_note(method: str, params: dict[str, Any]) -> None:
                await self._notified(spec.id, holder[0], method, params)

            client = MCPClient(
                transport, request_timeout=LIST_TIMEOUT_S, on_notification=on_note, on_close=on_close
            )
            holder.append(client)
            live.client = client
            try:
                live.handshake = await client.connect(timeout_s=self._connect_timeout)
                await self._discover(live)
            except MCPError as exc:
                return await self._failed(live, exc.message, actor)
            except Exception as exc:
                log.exception("MCP server %s failed to start", spec.name)
                return await self._failed(
                    live, f"Unexpected error while starting ({type(exc).__name__}).", actor
                )
            live.status, live.error, live.started_at = "running", None, self._clock.now()
            await self._emit(
                EventType.MCP_SERVER_STARTED,
                live,
                {"tools": len(live.tools), "resources": len(live.resources), "prompts": len(live.prompts)},
                actor,
            )
            return live

    async def _failed(self, live: LiveServer, message: str, actor: str = "system") -> LiveServer:
        await self._teardown(live)
        live.status, live.error = "error", redact_text(message)
        await self._emit(EventType.MCP_SERVER_FAILED, live, {"message": live.error}, actor)
        return live

    async def _teardown(self, live: LiveServer) -> None:
        self._registry.unregister_source(live.spec.source)
        if live.refresh_task is not None and not live.refresh_task.done():
            live.refresh_task.cancel()
        client, live.client = live.client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.close()

    async def stop(self, server_id: str, *, actor: str = "system", quiet: bool = False) -> LiveServer | None:
        async with self._lock(server_id):
            live = self._live.get(server_id)
            if live is None:
                return None
            was = live.status
            await self._teardown(live)
            live.status, live.error = "stopped", None
            if not quiet and was in ("running", "starting"):
                await self._emit(EventType.MCP_SERVER_STOPPED, live, {}, actor)
            return live

    async def forget(self, server_id: str) -> None:
        await self.stop(server_id, quiet=True)
        self._live.pop(server_id, None)
        self._locks.pop(server_id, None)

    async def shutdown(self) -> None:
        for live in list(self._live.values()):
            with contextlib.suppress(Exception):
                await self._teardown(live)
            live.status = "stopped"

    async def _lost(self, server_id: str, client: MCPClient, reason: str) -> None:
        """The connection ended without NEXUS asking (the program exited, the session was dropped)."""
        live = self._live.get(server_id)
        if live is None or live.client is not client or live.status != "running":
            return
        live.client = None
        self._registry.unregister_source(live.spec.source)
        live.status, live.error = "error", redact_text(reason)
        asyncio.get_running_loop().create_task(client.close())
        await self._emit(EventType.MCP_SERVER_FAILED, live, {"message": live.error})

    async def _notified(self, server_id: str, client: MCPClient, method: str, params: dict[str, Any]) -> None:
        live = self._live.get(server_id)
        if live is None or live.client is not client:
            return
        if method == "notifications/message":
            level = clean_text(params.get("level"), 20) or "info"
            data = params.get("data")
            text = data if isinstance(data, str) else json.dumps(data, default=str)
            live.log.add(f"[{level}] {clean_text(text, 400)}")
        elif method.endswith("/list_changed") and (live.refresh_task is None or live.refresh_task.done()):
            live.refresh_task = asyncio.get_running_loop().create_task(self._refresh(server_id))

    async def _refresh(self, server_id: str) -> None:
        await asyncio.sleep(0.2)  # a burst of change notices becomes one refresh
        async with self._lock(server_id):
            live = self._live.get(server_id)
            if live is None or live.status != "running" or live.client is None:
                return
            before = {t.name for t in live.tools}
            try:
                await self._discover(live)
            except MCPError as exc:
                live.log.add(f"(nexus) could not refresh the tool list: {exc.message}")
                return
            after = {t.name for t in live.tools}
            await self._emit(
                EventType.MCP_TOOLS_CHANGED,
                live,
                {
                    "tools": len(after),
                    "added": sorted(after - before)[:20],
                    "removed": sorted(before - after)[:20],
                },
            )

    # ---- discovery -----------------------------------------------------------------------
    async def _discover(self, live: LiveServer) -> None:
        client = live.client
        assert client is not None and live.handshake is not None
        caps = live.handshake.capabilities
        try:
            raw_tools = await client.list_all("tools/list", "tools")
        except MCPError as exc:
            if exc.rpc_code != METHOD_NOT_FOUND or "tools" in caps:
                raise
            raw_tools = []
        live.resources = await self._optional_list(
            live, client, "resources" in caps, "resources/list", "resources"
        )
        live.prompts = await self._optional_list(live, client, "prompts" in caps, "prompts/list", "prompts")
        await self._install(live, raw_tools)

    async def _optional_list(
        self, live: LiveServer, client: MCPClient, offered: bool, method: str, key: str
    ) -> list[dict[str, Any]]:
        if not offered:
            return []
        try:
            return await client.list_all(method, key)
        except MCPError as exc:  # a broken resource list should not cost the person the server's tools
            live.log.add(f"(nexus) {method} failed: {exc.message}")
            return []

    async def _install(self, live: LiveServer, raw_tools: list[dict[str, Any]]) -> None:
        spec = live.spec
        tools: list[DiscoveredTool] = []
        skipped: list[str] = []
        taken: set[str] = set()
        for raw in raw_tools:
            original = raw.get("name")
            if not isinstance(original, str) or not original.strip() or len(original) > 128:
                skipped.append("A tool without a usable name.")
                continue
            shown = clean_text(original, 128)
            if len(tools) >= MAX_TOOLS:
                skipped.append(f"{shown}: more than {MAX_TOOLS} tools; the rest were left out.")
                break
            try:
                schema = clean_schema(raw.get("inputSchema"))
            except ValueError as exc:
                skipped.append(f"{shown}: {exc}.")
                continue
            annotations = raw.get("annotations")
            title_raw = raw.get("title")
            if not isinstance(title_raw, str) and isinstance(annotations, dict):
                title_raw = annotations.get("title")
            title = clean_text(title_raw, 120)
            description = (
                clean_text(raw.get("description"), MAX_DESCRIPTION) or "(The server gave no description.)"
            )
            findings = scan_for_injection("\n".join([description, title, *_schema_texts(schema)]))
            flag = (
                "Its description contains text that looks like instructions to an AI "
                f"({', '.join(sorted({f.label for f in findings}))}). Read it before turning it on."
                if findings
                else None
            )
            tools.append(
                DiscoveredTool(
                    name=registered_name(spec.name, original, taken),
                    original=original,
                    title=title,
                    description=description,
                    schema=schema,
                    hints=_hints(annotations),
                    fingerprint=_fingerprint(raw),
                    flag=flag,
                )
            )
        self._registry.unregister_source(spec.source)
        for tool in tools:
            self._registry.register(self._definition(spec, tool))
        live.tools, live.skipped = tools, skipped
        switched_off = await self._rows.sync_source(
            spec.source,
            [
                {
                    "name": t.name,
                    "source": spec.source,
                    "description": t.description,
                    "input_schema": t.schema,
                    "output_schema": None,
                    "risk_level": spec.risk_level.value,
                    "requires_approval": False,
                    "capabilities": [Capability.MCP.value],
                    "fingerprint": t.fingerprint,
                    "flag": t.flag,
                }
                for t in tools
            ],
        )
        for name, reason in switched_off:
            await self._bus.emit(
                EventType.SECURITY_FLAG,
                payload={
                    "source": spec.source,
                    "tool": name,
                    "findings": ["mcp_tool_definition"],
                    "excerpt": reason[:300],
                },
            )

    def _definition(self, spec: ServerSpec, tool: DiscoveredTool) -> ToolDefinition:
        impact = (
            f"Sends these arguments to the MCP server “{spec.name}”, which runs its tool “{clean_text(tool.original, 128)}”. "
            "What that tool does is up to the server."
        )
        if tool.hints:
            impact += " " + " ".join(tool.hints)
        server_id, original = spec.id, tool.original

        async def handler(ctx: ToolContext, args: MCPArguments) -> str:
            return await self.call_tool(server_id, original, args.arguments())

        return ToolDefinition(
            name=tool.name,
            description=tool.description,
            input_schema=args_model(tool.name, tool.schema),
            risk_level=spec.risk_level,
            handler=handler,
            permissions=frozenset({Capability.MCP}),
            describe_impact=lambda _args: impact,
            returns_untrusted=True,
            source_label=lambda _args: f"mcp:{spec.name}/{clean_text(original, 128)}",
            timeout_s=spec.timeout_s + 5,  # the server's own limit fires first, with a clearer message
            source=spec.source,
        )

    # ---- calls ---------------------------------------------------------------------------
    def _running(self, server_id: str) -> tuple[LiveServer, MCPClient]:
        live = self._live.get(server_id)
        if live is None or live.status != "running" or live.client is None:
            name = live.spec.name if live else "that server"
            raise MCPError(f"The MCP server '{name}' is not running.", code="unavailable")
        return live, live.client

    async def call_tool(self, server_id: str, original: str, arguments: dict[str, Any]) -> str:
        try:
            live, client = self._running(server_id)
        except MCPError as exc:
            raise ToolError(
                f"{exc.message} It can be started in Settings → Integrations.", code="mcp_unavailable"
            ) from None
        try:
            result = await client.call_tool(original, arguments, timeout_s=live.spec.timeout_s)
        except MCPError as exc:
            raise ToolError(exc.message, code=f"mcp_{exc.code}", retryable=exc.retryable) from None
        text, is_error = render_tool_result(result)
        if is_error:
            raise ToolError(
                f"The tool reported an error: {text[:2000] or 'no details given'}", code="mcp_tool_error"
            )
        return text or "(The tool returned nothing.)"

    async def read_resource(self, server_id: str, uri: str) -> list[dict[str, Any]]:
        _, client = self._running(server_id)
        return render_resource(await client.read_resource(uri))

    async def get_prompt(self, server_id: str, name: str, arguments: dict[str, str]) -> list[dict[str, str]]:
        _, client = self._running(server_id)
        return render_prompt(await client.get_prompt(name, arguments))

    async def check(self, server_id: str) -> tuple[bool, float | None, str]:
        """Ping a running server: (answered, round trip ms, what happened)."""
        try:
            _, client = self._running(server_id)
            latency = await client.ping()
        except MCPError as exc:
            return False, None, exc.message
        return True, round(latency, 1), "Answered a ping."
