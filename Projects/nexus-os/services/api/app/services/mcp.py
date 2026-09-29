"""MCP servers (Settings → Integrations): configuration, secrets, lifecycle and status.

Secret values (environment variables and HTTP headers marked secret) go straight to the secret store;
the database and every response only name them. A plain value that looks like a secret, or a plainly
named credential (``*_TOKEN``, ``Authorization``), is refused so it cannot end up stored in the clear.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, InvalidRequestError
from app.core.ids import new_id
from app.core.risk import RiskLevel
from app.core.secrets import SecretStore
from app.core.security import find_secrets, redact_text
from app.events.bus import EventBus
from app.events.types import EventType
from app.mcp.jsonschema import clean_text
from app.mcp.manager import LiveServer, MCPServerManager, ServerSpec
from app.mcp.protocol import MCPError
from app.mcp.transport import is_loopback, server_env
from app.repositories.integration_store import IntegrationStore
from app.repositories.runtime_store import ToolRowStore
from app.schemas.health import HealthCheckResult
from app.schemas.mcp import (
    ENV_NAME,
    HEADER_NAME,
    IntegrationRecord,
    MCPHealth,
    MCPPromptArgument,
    MCPPromptOut,
    MCPResourceOut,
    MCPServerConfig,
    MCPServerCreate,
    MCPServerDetail,
    MCPServerOut,
    MCPServerUpdate,
    MCPToolOut,
    PromptMessage,
    ResourceContent,
)

KIND = "mcp"
MAX_ENTRIES = 50
STARTUP_WAIT_S = 5.0
_CREDENTIAL_NAME = re.compile(
    r"(?i)(token|secret|passw(or)?d|api[_-]?key|(^|[_-])key$|private[_-]?key|credential|auth|cookie|session)"
)


def _secret_name(server_id: str, kind: str, key: str) -> str:
    return f"mcp:{server_id}:{kind}:{key.lower()}"


def _check_pairs(label: str, plain: dict[str, str], secret: list[str], pattern: str) -> None:
    if len(plain) + len(secret) > MAX_ENTRIES:
        raise InvalidRequestError(f"At most {MAX_ENTRIES} {label}s.")
    lowered: set[str] = set()
    for key in [*plain, *secret]:
        if not re.match(pattern, key):
            raise InvalidRequestError(f"'{clean_text(key, 60)}' is not a valid {label} name.")
        if key.lower() in lowered:
            raise InvalidRequestError(f"The {label} {key} is set twice.")
        lowered.add(key.lower())
    for key, value in plain.items():
        if len(value) > 4000 or "\x00" in value:
            raise InvalidRequestError(f"The value of {key} is too long.")
        if (
            _CREDENTIAL_NAME.search(key)
            or find_secrets(value, generic=False)
            or find_secrets(f"{key}={value}")
        ):
            raise InvalidRequestError(
                f"{key} looks like a credential. Add it as a secret value instead, so it is kept in the "
                "secret store and never shown again."
            )


def validate_config(cfg: MCPServerConfig) -> None:
    if cfg.transport == "stdio":
        if not cfg.command.strip():
            raise InvalidRequestError("Give the command that starts the server, e.g. 'npx' or 'uvx'.")
        if any(c in cfg.command for c in "\n\r\x00"):
            raise InvalidRequestError("The command must be a single line.")
        if any(len(a) > 2000 or "\x00" in a for a in cfg.args):
            raise InvalidRequestError("An argument is too long.")
        if cfg.cwd and not Path(cfg.cwd).is_absolute():
            raise InvalidRequestError("The working folder must be a full path.")
        _check_pairs("environment variable", cfg.env, cfg.secret_env, ENV_NAME)
        for a in cfg.args:
            if find_secrets(a):
                raise InvalidRequestError(
                    "An argument looks like a credential. Pass it as a secret environment variable instead."
                )
    else:
        parsed = urlparse(cfg.url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise InvalidRequestError("The address must start with http:// or https:// and include a host.")
        if parsed.username or parsed.password or parsed.fragment:
            raise InvalidRequestError("The address must not contain a user name, password or #fragment.")
        if find_secrets(cfg.url):
            raise InvalidRequestError(
                "The address looks like it contains a token. Send it as a secret header instead."
            )
        _check_pairs("header", cfg.headers, cfg.secret_headers, HEADER_NAME)
        if parsed.scheme == "http" and cfg.secret_headers and not is_loopback(cfg.url):
            raise InvalidRequestError(
                "Secret headers would be sent unencrypted. Use https:// for remote servers."
            )
    if cfg.risk_level is RiskLevel.SAFE:
        raise InvalidRequestError(
            "MCP tools act outside NEXUS's own checks, so the lowest level they can have is moderate."
        )


class MCPService:
    def __init__(
        self,
        store: IntegrationStore,
        manager: MCPServerManager,
        tool_rows: ToolRowStore,
        secrets: SecretStore,
        bus: EventBus,
        home: Path,
        clock: Clock | None = None,
    ) -> None:
        self._store = store
        self._manager = manager
        self._rows = tool_rows
        self._secrets = secrets
        self._bus = bus
        self._home = home
        self._clock = clock or SystemClock()
        self._background: set[asyncio.Task[Any]] = set()

    # ---- reading -------------------------------------------------------------------------
    def _out(self, rec: IntegrationRecord) -> MCPServerOut:
        cfg = MCPServerConfig.model_validate(rec.config)
        live = self._manager.live(rec.id)
        running = live is not None and live.status == "running"
        if live is not None and live.status != "stopped":
            status, error = live.status, live.error
        else:
            status = "error" if rec.enabled and rec.last_error else "stopped"
            error = rec.last_error if rec.enabled else None
        hs = live.handshake if live is not None and running else None
        return MCPServerOut(
            id=rec.id,
            name=rec.name,
            description=cfg.description,
            transport=cfg.transport,
            command=cfg.command,
            args=cfg.args,
            cwd=cfg.cwd,
            env=cfg.env,
            url=cfg.url,
            headers=cfg.headers,
            secret_env=cfg.secret_env,
            secret_headers=cfg.secret_headers,
            risk_level=cfg.risk_level,
            timeout_s=cfg.timeout_s,
            enabled=rec.enabled,
            status=status,
            error=error,
            server_name=hs.name if hs else None,
            server_version=hs.version if hs else None,
            protocol_version=hs.protocol_version if hs else None,
            tools=len(live.tools) if live is not None and running else 0,
            resources=len(live.resources) if live is not None and running else 0,
            prompts=len(live.prompts) if live is not None and running else 0,
            started_at=live.started_at if live is not None and running else None,
            last_health=MCPHealth.model_validate(rec.last_health) if rec.last_health else None,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
        )

    async def list_servers(self) -> list[MCPServerOut]:
        return [self._out(r) for r in await self._store.list_kind(KIND)]

    async def get(self, server_id: str) -> MCPServerOut:
        return self._out(await self._record(server_id))

    async def _record(self, server_id: str) -> IntegrationRecord:
        rec = await self._store.get(server_id)
        if rec.kind != KIND:
            raise InvalidRequestError("That is not an MCP server.")
        return rec

    async def detail(self, server_id: str) -> MCPServerDetail:
        rec = await self._record(server_id)
        live = self._manager.live(server_id)
        running = live is not None and live.status == "running"
        rows = {t.name: t for t in await self._rows.list_tools() if t.source == f"mcp:{rec.name}"}
        tools = []
        if live is not None and running:
            for t in live.tools:
                row = rows.get(t.name)
                tools.append(
                    MCPToolOut(
                        name=t.name,
                        original_name=clean_text(t.original, 128),
                        title=t.title,
                        description=t.description,
                        input_schema=t.schema,
                        hints=t.hints,
                        enabled=row.enabled if row else True,
                        note=row.note if row else None,
                    )
                )
        else:  # stopped: what NEXUS last saw, so choices can still be made
            for row in rows.values():
                tools.append(
                    MCPToolOut(
                        name=row.name,
                        original_name=row.name.split("__", 2)[-1],
                        description=row.description,
                        input_schema=row.input_schema,
                        enabled=row.enabled,
                        note=row.note,
                    )
                )
        return MCPServerDetail(
            server=self._out(rec),
            instructions=live.handshake.instructions
            if live is not None and running and live.handshake
            else "",
            tools=tools,
            resources=[_resource(r) for r in live.resources] if live is not None and running else [],
            prompts=[_prompt(p) for p in live.prompts] if live is not None and running else [],
            skipped=live.skipped if live is not None and running else [],
        )

    async def log(self, server_id: str) -> list[str]:
        await self._record(server_id)
        live = self._manager.live(server_id)
        return live.log.lines() if live is not None else []

    # ---- configuration -------------------------------------------------------------------
    async def create(self, data: MCPServerCreate) -> MCPServerOut:
        server_id = new_id(KIND)
        cfg = MCPServerConfig(
            transport=data.transport,
            description=data.description.strip(),
            command=data.command.strip(),
            args=data.args,
            cwd=data.cwd or None,
            env=data.env,
            url=data.url.strip(),
            headers=data.headers,
            secret_env=list(data.secret_env),
            secret_headers=list(data.secret_headers),
            risk_level=data.risk_level,
            timeout_s=data.timeout_s,
        )
        _only_transport(cfg)
        validate_config(cfg)
        if any(r.name == data.name for r in await self._store.list_kind(KIND)):
            raise ConflictError(f"There is already a server called '{data.name}'.")
        written: list[str] = []
        try:
            for key, value in data.secret_env.items():
                written.append(_secret_name(server_id, "env", key))
                await self._secrets.set(written[-1], value)
            for key, value in data.secret_headers.items():
                written.append(_secret_name(server_id, "header", key))
                await self._secrets.set(written[-1], value)
            rec = await self._store.create(
                kind=KIND,
                name=data.name,
                config=cfg.model_dump(mode="json"),
                enabled=data.enabled,
                id_=server_id,
            )
        except Exception:
            for name in written:  # never orphan a secret for a server that was not saved
                with contextlib.suppress(Exception):
                    await self._secrets.delete(name)
            raise
        await self._bus.emit(
            EventType.MCP_SERVER_ADDED,
            actor="user",
            payload={
                "server_id": rec.id,
                "name": rec.name,
                "transport": cfg.transport,
                "risk": cfg.risk_level.value,
            },
        )
        if rec.enabled:
            await self._start(rec, actor="user")
        return await self.get(rec.id)

    async def update(self, server_id: str, data: MCPServerUpdate) -> MCPServerOut:
        rec = await self._record(server_id)
        cfg = MCPServerConfig.model_validate(rec.config)
        was_enabled = rec.enabled
        changes = data.model_dump(exclude_unset=True)
        enabled = changes.pop("enabled", rec.enabled)
        secret_env = changes.pop("secret_env", None) or {}
        secret_headers = changes.pop("secret_headers", None) or {}
        updated = MCPServerConfig.model_validate(
            {**cfg.model_dump(), **{k: (v.strip() if isinstance(v, str) else v) for k, v in changes.items()}}
        )
        updated.secret_env = _merge_names(cfg.secret_env, secret_env)
        updated.secret_headers = _merge_names(cfg.secret_headers, secret_headers)
        if updated.cwd == "":
            updated.cwd = None
        _only_transport(updated)
        validate_config(updated)
        for kind, items in (("env", secret_env), ("header", secret_headers)):
            for key, value in items.items():
                name = _secret_name(server_id, kind, key)
                if value is None:
                    await self._secrets.delete(name)
                else:
                    await self._secrets.set(name, value)
        rec = await self._store.update(
            server_id,
            config=updated.model_dump(mode="json"),
            enabled=enabled,
            **({"last_error": None} if not enabled else {}),
        )
        changed = sorted(
            {
                *changes,
                *(["secret_env"] if secret_env else []),
                *(["secret_headers"] if secret_headers else []),
            }
        )
        if enabled != was_enabled:
            changed.append("enabled")
        await self._bus.emit(
            EventType.MCP_SERVER_UPDATED,
            actor="user",
            payload={"server_id": rec.id, "name": rec.name, "changed": changed},
        )
        live = self._manager.live(server_id)
        # Anything the running server depends on (not just its description) means a restart.
        relaunch = (
            updated.model_copy(update={"description": ""}) != cfg.model_copy(update={"description": ""})
            or bool(secret_env)
            or bool(secret_headers)
        )
        if not enabled:
            await self._manager.stop(server_id, actor="user")
        elif live is None or live.status != "running" or relaunch:
            await self._manager.stop(server_id, quiet=True)
            await self._start(rec, actor="user")
        return await self.get(server_id)

    async def delete(self, server_id: str) -> None:
        rec = await self._record(server_id)
        cfg = MCPServerConfig.model_validate(rec.config)
        await self._manager.forget(server_id)
        await self._rows.delete_source(f"mcp:{rec.name}")
        for key in cfg.secret_env:
            await self._secrets.delete(_secret_name(server_id, "env", key))
        for key in cfg.secret_headers:
            await self._secrets.delete(_secret_name(server_id, "header", key))
        await self._store.delete(server_id)
        await self._bus.emit(
            EventType.MCP_SERVER_REMOVED, actor="user", payload={"server_id": rec.id, "name": rec.name}
        )

    # ---- lifecycle -----------------------------------------------------------------------
    async def _spec(self, rec: IntegrationRecord) -> ServerSpec:
        cfg = MCPServerConfig.model_validate(rec.config)
        env, headers = dict(cfg.env), dict(cfg.headers)
        for kind, names, target in (("env", cfg.secret_env, env), ("header", cfg.secret_headers, headers)):
            for key in names:
                value = await self._secrets.get(_secret_name(rec.id, kind, key))
                if value is None:
                    raise MCPError(
                        f"The secret value for {key} is missing. Enter it again.", code="missing_secret"
                    )
                target[key] = value
        cwd = Path(cfg.cwd) if cfg.cwd else self._home / "mcp" / rec.name
        if not cfg.cwd:
            cwd.mkdir(parents=True, exist_ok=True)
        return ServerSpec(
            id=rec.id,
            name=rec.name,
            transport=cfg.transport,
            command=cfg.command,
            args=cfg.args,
            cwd=cwd,
            env=server_env(env) if cfg.transport == "stdio" else {},
            url=cfg.url,
            headers=headers,
            risk_level=cfg.risk_level,
            timeout_s=cfg.timeout_s,
        )

    async def _start(self, rec: IntegrationRecord, *, actor: str) -> LiveServer | None:
        try:
            spec = await self._spec(rec)
        except MCPError as exc:
            await self._store.update(rec.id, last_error=exc.message)
            await self._bus.emit(
                EventType.MCP_SERVER_FAILED,
                actor=actor,
                payload={"server_id": rec.id, "name": rec.name, "message": exc.message},
            )
            return None
        live = await self._manager.start(spec, actor=actor)
        if live.status == "running":
            health = MCPHealth(ok=True, checked_at=self._clock.now(), message="Connected.")
            await self._store.update(rec.id, last_error=None, last_health=health.model_dump(mode="json"))
        else:
            await self._store.update(rec.id, last_error=live.error)
        return live

    async def start(self, server_id: str) -> MCPServerOut:
        rec = await self._record(server_id)
        if not rec.enabled:
            rec = await self._store.update(server_id, enabled=True)
        await self._start(rec, actor="user")
        return await self.get(server_id)

    async def stop(self, server_id: str) -> MCPServerOut:
        await self._record(server_id)
        await self._manager.stop(server_id, actor="user")
        rec = await self._store.update(server_id, enabled=False, last_error=None)
        return self._out(rec)

    async def check(self, server_id: str) -> MCPServerOut:
        rec = await self._record(server_id)
        ok, latency, message = await self._manager.check(server_id)
        health = MCPHealth(
            ok=ok, checked_at=self._clock.now(), latency_ms=latency, message=redact_text(message)
        )
        rec = await self._store.update(server_id, last_health=health.model_dump(mode="json"))
        return self._out(rec)

    async def read_resource(self, server_id: str, uri: str) -> list[ResourceContent]:
        await self._record(server_id)
        try:
            return [
                ResourceContent.model_validate(c) for c in await self._manager.read_resource(server_id, uri)
            ]
        except MCPError as exc:
            raise ConflictError(exc.message) from None

    async def get_prompt(self, server_id: str, name: str, arguments: dict[str, str]) -> list[PromptMessage]:
        await self._record(server_id)
        try:
            return [
                PromptMessage.model_validate(m)
                for m in await self._manager.get_prompt(server_id, name, arguments)
            ]
        except MCPError as exc:
            raise ConflictError(exc.message) from None

    async def start_enabled(self, *, wait_s: float = STARTUP_WAIT_S) -> None:
        """Start every switched-on server in the background. Waits briefly, so servers that come up
        quickly have their tools registered before interrupted runs resume."""
        tasks = []
        for rec in await self._store.list_kind(KIND):
            if rec.enabled:
                task = asyncio.get_running_loop().create_task(self._start(rec, actor="system"))
                self._background.add(task)
                task.add_done_callback(self._background.discard)
                tasks.append(task)
        if tasks:
            await asyncio.wait(tasks, timeout=wait_s)

    async def shutdown(self) -> None:
        for task in list(self._background):
            task.cancel()
        for task in list(self._background):
            with contextlib.suppress(BaseException):
                await task
        await self._manager.shutdown()

    async def health_check(self) -> HealthCheckResult:
        servers = [s for s in await self.list_servers() if s.enabled]
        if not servers:
            return HealthCheckResult(
                name="mcp", label="MCP servers", status="ok", detail="No MCP servers are switched on."
            )
        down = [s.name for s in servers if s.status != "running"]
        detail = f"{len(servers) - len(down)} of {len(servers)} running"
        if down:
            detail += f"; not running: {', '.join(down)}"
        return HealthCheckResult(
            name="mcp",
            label="MCP servers",
            status="degraded" if down else "ok",
            detail=detail,
            data={"down": down},
        )


def _only_transport(cfg: MCPServerConfig) -> None:
    """Drop the other transport's fields so a switch never leaves stale settings behind."""
    if cfg.transport == "stdio":
        cfg.url, cfg.headers, cfg.secret_headers = "", {}, []
    else:
        cfg.command, cfg.args, cfg.cwd, cfg.env, cfg.secret_env = "", [], None, {}, []


def _merge_names(current: list[str], changes: dict[str, str | None]) -> list[str]:
    names = [n for n in current if changes.get(n, "") is not None]
    for key, value in changes.items():
        if value is not None and key not in names:
            names.append(key)
    return names


def _resource(raw: dict[str, Any]) -> MCPResourceOut:
    return MCPResourceOut(
        uri=clean_text(raw.get("uri"), 500),
        name=clean_text(raw.get("name"), 120) or clean_text(raw.get("uri"), 120),
        description=clean_text(raw.get("description"), 400),
        mime_type=clean_text(raw.get("mimeType"), 120) or None,
    )


def _prompt(raw: dict[str, Any]) -> MCPPromptOut:
    raw_args = raw.get("arguments")
    args: list[Any] = raw_args if isinstance(raw_args, list) else []
    return MCPPromptOut(
        name=clean_text(raw.get("name"), 120),
        description=clean_text(raw.get("description"), 400),
        arguments=[
            MCPPromptArgument(
                name=clean_text(a.get("name"), 80),
                description=clean_text(a.get("description"), 200),
                required=a.get("required") is True,
            )
            for a in args
            if isinstance(a, dict)
        ],
    )
