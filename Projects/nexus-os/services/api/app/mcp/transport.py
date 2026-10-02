"""MCP transports: stdio (a program on this computer) and streamable HTTP (a web address).

A transport moves JSON-RPC messages; the client matches requests and responses. Incoming messages are
handed to ``on_message``; a connection that ends on its own (the program exited, the server dropped
the session) is reported once through ``on_close``.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
import shutil
import signal
import subprocess
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from app.core.security import redact_text
from app.mcp.protocol import MAX_MESSAGE_BYTES, MCPError

IS_WINDOWS = os.name == "nt"
SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)  # Windows has no SIGKILL; kill() is used there
LOG_LINES = 200
LOG_LINE_CHARS = 500

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]
CloseHandler = Callable[[str], Awaitable[None]]

# What a server program inherits from NEXUS's own environment: enough to start and reach the network,
# and nothing else (no API keys, no NEXUS_* settings). Everything else must be configured explicitly.
INHERITED_ENV = (
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    # Windows needs these to start most programs
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "USERPROFILE",
)


def server_env(configured: dict[str, str]) -> dict[str, str]:
    env = {k: os.environ[k] for k in INHERITED_ENV if k in os.environ}
    env.update(configured)
    return env


class LogTail:
    """The last lines a server wrote about itself (stderr, stray stdout, log notifications), redacted."""

    def __init__(self) -> None:
        self._lines: deque[str] = deque(maxlen=LOG_LINES)

    def add(self, line: str) -> None:
        text = redact_text(line.rstrip())
        if text:
            self._lines.append(text[:LOG_LINE_CHARS])

    def lines(self) -> list[str]:
        return list(self._lines)


async def _noop_message(_: dict[str, Any]) -> None:
    return None


async def _noop_close(_: str) -> None:
    return None


class Transport(ABC):
    def __init__(self) -> None:
        self.on_message: MessageHandler = _noop_message
        self.on_close: CloseHandler = _noop_close
        self.log = LogTail()

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send(self, message: dict[str, Any]) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    def negotiated(self, protocol_version: str) -> None:  # noqa: B027 - optional hook
        """Called once the protocol version is agreed."""

    async def _deliver(self, payload: Any) -> None:
        for message in payload if isinstance(payload, list) else [payload]:
            if isinstance(message, dict):
                await self.on_message(message)


class StdioTransport(Transport):
    """Runs the server as a child process and speaks newline-delimited JSON on its stdin/stdout.

    The process gets its own process group so stopping it also stops anything it started. It runs with
    the person's own permissions: NEXUS does not sandbox MCP servers (they are programs the person
    chose to add), but it does not hand them its own environment either."""

    def __init__(self, command: str, args: list[str], env: dict[str, str], cwd: Path) -> None:
        super().__init__()
        self._command = command
        self._args = args
        self._env = env
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._write_lock = asyncio.Lock()
        self._closing = False
        self._report: asyncio.Future[None] | None = None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    async def start(self) -> None:
        exe = shutil.which(self._command, path=self._env.get("PATH"))
        if exe is None and os.path.isabs(self._command) and os.access(self._command, os.X_OK):
            exe = self._command
        if exe is None:
            raise MCPError(
                f"Could not find the program '{self._command}'. Check the command, or give its full path.",
                code="not_found",
            )
        if not self._cwd.is_dir():
            raise MCPError(f"The working folder {self._cwd} does not exist.", code="bad_config")
        kwargs: dict[str, Any] = {}
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        try:
            self._proc = await asyncio.create_subprocess_exec(
                exe,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
                cwd=self._cwd,
                limit=MAX_MESSAGE_BYTES,
                **kwargs,
            )
        except (PermissionError, OSError) as exc:
            raise MCPError(
                f"Could not start '{self._command}' ({type(exc).__name__}).", code="start_failed"
            ) from None
        self._tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._read_stderr())]

    async def _read(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        reason = ""
        try:
            while True:
                try:
                    line = await self._proc.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    reason = "The server sent a message larger than 4 MB, so NEXUS disconnected."
                    break
                if not line:
                    break
                text = line.decode("utf-8", "replace").strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    self.log.add(f"(stdout) {text}")  # a log line on the wrong stream: keep it, skip it
                    continue
                await self._deliver(payload)
        finally:
            if not self._closing:
                if not reason:
                    code = None
                    with contextlib.suppress(TimeoutError):
                        code = await asyncio.wait_for(self._proc.wait(), 2)
                    reason = "The server program ended" + (
                        f" (exit code {code})." if code is not None else "."
                    )
                self._closing = True
                await self._kill()
                # Reported from its own task: whoever handles it may close this transport, which cancels
                # this reader, and the report must not be cut short by that.
                self._report = asyncio.ensure_future(self.on_close(reason))

    async def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        with contextlib.suppress(ValueError, asyncio.LimitOverrunError):
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
                self.log.add(line.decode("utf-8", "replace"))

    async def send(self, message: dict[str, Any]) -> None:
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        async with self._write_lock:
            proc = self._proc
            if proc is None or proc.stdin is None or proc.returncode is not None or self._closing:
                raise MCPError("The server is not running.", code="closed")
            try:
                proc.stdin.write(data)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                raise MCPError("The server stopped reading.", code="closed") from None

    def _signal_group(self, sig: int) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            if not IS_WINDOWS:
                os.killpg(proc.pid, sig)
            elif sig == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()

    async def _kill(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.returncode is None:
            if proc.stdin is not None:
                with contextlib.suppress(Exception):
                    proc.stdin.close()  # a well-behaved server exits when its input ends
            try:
                await asyncio.wait_for(proc.wait(), 2)
            except TimeoutError:
                self._signal_group(signal.SIGTERM)
                try:
                    await asyncio.wait_for(proc.wait(), 3)
                except TimeoutError:
                    self._signal_group(SIGKILL)
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(proc.wait(), 3)
        # Children the server started keep running in its group otherwise.
        if not IS_WINDOWS:
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(proc.pid, SIGKILL)

    async def close(self) -> None:
        self._closing = True
        await self._kill()
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task


def is_loopback(url: str) -> bool:
    host = httpx.URL(url).host
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def new_http_client() -> httpx.AsyncClient:
    """A client for one server: no redirects (headers can carry credentials; they must never be replayed
    to another host), and loopback addresses never go through a system proxy."""
    loopback = {f"all://{h}": httpx.AsyncHTTPTransport() for h in ("localhost", "127.0.0.1", "[::1]")}
    return httpx.AsyncClient(
        timeout=httpx.Timeout(300.0, connect=10.0), follow_redirects=False, mounts=loopback
    )


class HttpTransport(Transport):
    """Streamable HTTP: every message is a POST; the answer comes back as JSON or as a short
    server-sent-event stream. The session id the server hands out on ``initialize`` goes with every later
    request. (The older HTTP+SSE transport is not supported.)"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str],
        client_factory: Callable[[], httpx.AsyncClient] = new_http_client,
    ) -> None:
        super().__init__()
        self._url = url
        self._headers = headers
        self._factory = client_factory
        self._client: httpx.AsyncClient | None = None
        self._session: str | None = None
        self._version: str | None = None
        self._closed = False

    async def start(self) -> None:
        self._client = self._factory()

    def negotiated(self, protocol_version: str) -> None:
        self._version = protocol_version

    def _request_headers(self) -> dict[str, str]:
        headers = {
            **self._headers,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        if self._version:
            headers["MCP-Protocol-Version"] = self._version
        return headers

    async def send(self, message: dict[str, Any]) -> None:
        if self._client is None or self._closed:
            raise MCPError("Not connected to the server.", code="closed")
        wanted = message.get("id") if "method" in message else None
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            async with self._client.stream(
                "POST", self._url, content=body, headers=self._request_headers()
            ) as resp:
                sid = resp.headers.get("mcp-session-id")
                if message.get("method") == "initialize" and sid:
                    if not sid.isascii() or not sid.isprintable() or len(sid) > 256:
                        raise MCPError("The server sent an invalid session id.", code="protocol")
                    self._session = sid
                await self._handle(resp, wanted)
        except httpx.TimeoutException:
            raise MCPError("The server did not answer in time.", code="timeout", retryable=True) from None
        except httpx.HTTPError as exc:
            raise MCPError(
                f"Could not reach the server ({type(exc).__name__}).", code="unreachable", retryable=True
            ) from None

    async def _handle(self, resp: httpx.Response, wanted: Any) -> None:
        status = resp.status_code
        if status == 202:
            return
        if status == 404 and self._session:
            self._closed = True
            await self.on_close("The server ended the session. Start the server again to reconnect.")
            raise MCPError("The server ended the session.", code="closed")
        if status in (401, 403):
            raise MCPError(
                f"The server refused the request (HTTP {status}). Check its headers or token.",
                code="unauthorized",
            )
        if 300 <= status < 400:
            raise MCPError(
                f"The server redirected the request (HTTP {status}); NEXUS does not follow redirects. "
                "Use the final address.",
                code="redirect",
            )
        if status >= 400:
            raise MCPError(f"The server answered HTTP {status}.", code="http_error", retryable=status >= 500)
        kind = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if kind == "text/event-stream":
            await self._read_events(resp, wanted)
            return
        raw = bytearray()
        async for chunk in resp.aiter_bytes():
            raw += chunk
            if len(raw) > MAX_MESSAGE_BYTES:
                raise MCPError("The server sent a message larger than 4 MB.", code="too_large")
        if not raw.strip():
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise MCPError("The server sent something that is not JSON.", code="protocol") from None
        await self._deliver(payload)

    async def _read_events(self, resp: httpx.Response, wanted: Any) -> None:
        data: list[str] = []
        size = 0
        async for line in resp.aiter_lines():
            size += len(line)
            if size > MAX_MESSAGE_BYTES:
                raise MCPError("The server sent more than 4 MB in one answer.", code="too_large")
            if line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
                continue
            if line.strip() or not data:
                continue  # event:, id:, retry: and comments carry nothing NEXUS needs
            text, data = "\n".join(data), []
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            await self._deliver(payload)
            answered = [
                p for p in (payload if isinstance(payload, list) else [payload]) if isinstance(p, dict)
            ]
            if wanted is not None and any(p.get("id") == wanted and "method" not in p for p in answered):
                return  # our answer arrived; the server may keep the stream open, NEXUS does not wait

    async def close(self) -> None:
        if self._client is None:
            return
        if self._session and not self._closed:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    self._client.delete(self._url, headers=self._request_headers()), timeout=3
                )
        self._closed = True
        with contextlib.suppress(Exception):
            await self._client.aclose()
        self._client = None
