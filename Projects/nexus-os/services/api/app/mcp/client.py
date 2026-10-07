"""MCPClient: one connection to one MCP server over any transport.

NEXUS is a minimal client: it declares no client capabilities (no sampling, roots or elicitation), so
a server's requests to it are answered "not supported" (except ``ping``). Requests time out, and a
timed-out or abandoned request is cancelled on the server with ``notifications/cancelled``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app import __version__
from app.mcp.jsonschema import clean_text
from app.mcp.protocol import (
    METHOD_NOT_FOUND,
    PROTOCOL_VERSION,
    SUPPORTED_VERSIONS,
    MCPError,
    rpc_error_message,
)
from app.mcp.transport import Transport

MAX_PAGES = 20
MAX_ITEMS = 500

NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
CloseHandler = Callable[[str], Awaitable[None]]


@dataclass
class Handshake:
    protocol_version: str
    name: str
    version: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""


class MCPClient:
    def __init__(
        self,
        transport: Transport,
        *,
        request_timeout: float = 30.0,
        on_notification: NotificationHandler | None = None,
        on_close: CloseHandler | None = None,
    ) -> None:
        self._transport = transport
        self._timeout = request_timeout
        self._on_notification = on_notification
        self._on_close = on_close
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._background: set[asyncio.Task[None]] = set()
        self.closed: str | None = None
        self.handshake: Handshake | None = None
        transport.on_message = self._dispatch
        transport.on_close = self._closed

    @property
    def transport(self) -> Transport:
        return self._transport

    # ---- lifecycle -----------------------------------------------------------------------
    async def connect(self, *, timeout_s: float = 30.0) -> Handshake:
        await self._transport.start()
        result = await self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "nexus-os", "title": "NEXUS OS", "version": __version__},
            },
            timeout_s=timeout_s,
        )
        version = result.get("protocolVersion")
        if version not in SUPPORTED_VERSIONS:
            raise MCPError(
                f"The server speaks MCP version {clean_text(str(version), 40)!r}; NEXUS supports "
                f"{', '.join(SUPPORTED_VERSIONS)}.",
                code="unsupported_version",
            )
        self._transport.negotiated(str(version))
        await self.notify("notifications/initialized")
        raw_info, raw_caps = result.get("serverInfo"), result.get("capabilities")
        info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
        caps: dict[str, Any] = raw_caps if isinstance(raw_caps, dict) else {}
        self.handshake = Handshake(
            protocol_version=str(version),
            name=clean_text(info.get("name"), 120),
            version=clean_text(info.get("version"), 60),
            capabilities=caps,
            instructions=clean_text(result.get("instructions"), 2000),
        )
        return self.handshake

    async def close(self) -> None:
        if self.closed is None:
            self.closed = "The connection was closed."
        self._fail_pending(self.closed)
        await self._transport.close()
        for task in list(self._background):
            task.cancel()

    # ---- messages ------------------------------------------------------------------------
    async def request(
        self, method: str, params: dict[str, Any] | None = None, *, timeout_s: float | None = None
    ) -> dict[str, Any]:
        if self.closed is not None:
            raise MCPError(self.closed, code="closed")
        self._next_id += 1
        rid = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[rid] = future
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            message["params"] = params
        limit = timeout_s or self._timeout
        try:
            async with asyncio.timeout(limit):
                await self._transport.send(message)
                return await future
        except TimeoutError:
            self._spawn(self._cancel_remote(rid, "timed out"))
            raise MCPError(
                f"The server did not answer {method} within {limit:g}s.", code="timeout", retryable=True
            ) from None
        except asyncio.CancelledError:
            self._spawn(self._cancel_remote(rid, "cancelled"))
            raise
        finally:
            self._pending.pop(rid, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self._transport.send(message)

    async def _cancel_remote(self, rid: int, reason: str) -> None:
        if self.closed is None and rid != 1:  # the initialize request must not be cancelled
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    self.notify("notifications/cancelled", {"requestId": rid, "reason": reason}), 5
                )

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if isinstance(method, str):
            if "id" in message:
                self._spawn(self._answer(message["id"], method))
            elif self._on_notification is not None:
                raw = message.get("params")
                params: dict[str, Any] = raw if isinstance(raw, dict) else {}
                with contextlib.suppress(Exception):
                    await self._on_notification(method, params)
            return
        rid = message.get("id")
        future = self._pending.get(rid) if isinstance(rid, int) else None
        if future is None or future.done():
            return
        if "error" in message:
            text, code = rpc_error_message(message["error"])
            future.set_exception(MCPError(text, code="rpc_error", rpc_code=code))
        else:
            result = message.get("result")
            future.set_result(result if isinstance(result, dict) else {})

    async def _answer(self, rid: Any, method: str) -> None:
        if method == "ping":
            reply: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "result": {}}
        else:
            reply = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": METHOD_NOT_FOUND, "message": "NEXUS does not support this request."},
            }
        with contextlib.suppress(Exception):
            await self._transport.send(reply)

    async def _closed(self, reason: str) -> None:
        if self.closed is not None:
            return
        self.closed = reason
        self._fail_pending(reason)
        if self._on_close is not None:
            await self._on_close(reason)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(MCPError(reason, code="closed"))

    # ---- MCP methods ---------------------------------------------------------------------
    async def list_all(self, method: str, key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            result = await self.request(method, {"cursor": cursor} if cursor else None)
            page = result.get(key)
            if isinstance(page, list):
                items.extend(x for x in page if isinstance(x, dict))
            nxt = result.get("nextCursor")
            cursor = nxt if isinstance(nxt, str) and nxt else None
            if cursor is None or len(items) >= MAX_ITEMS:
                break
        return items[:MAX_ITEMS]

    async def call_tool(self, name: str, arguments: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
        return await self.request("tools/call", {"name": name, "arguments": arguments}, timeout_s=timeout_s)

    async def read_resource(self, uri: str) -> dict[str, Any]:
        return await self.request("resources/read", {"uri": uri})

    async def get_prompt(self, name: str, arguments: dict[str, str]) -> dict[str, Any]:
        return await self.request("prompts/get", {"name": name, "arguments": arguments})

    async def ping(self, *, timeout_s: float = 10.0) -> float:
        """Round trip in milliseconds."""
        started = time.monotonic()
        await self.request("ping", timeout_s=timeout_s)
        return (time.monotonic() - started) * 1000
