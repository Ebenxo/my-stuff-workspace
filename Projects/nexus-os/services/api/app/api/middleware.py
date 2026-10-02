"""Security middleware for the local API.

Order of checks: Host (anti DNS-rebinding) → Origin allow-list → bearer token → rate limit →
body size. Every response gets hardening headers. Only ``PUBLIC_PATHS`` skip the token.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.ratelimit import RateLimiter
from app.core.security import constant_time_equals

PUBLIC_PATHS = frozenset({"/api/health/ping"})
RATE_EXEMPT_PREFIXES = ("/api/events/stream",)
SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "cross-origin-resource-policy": "same-site",
}


def _error(
    status: int, code: str, message: str, extra: dict[str, str] | None = None
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    body = json.dumps({"error": {"code": code, "message": message, "details": {}}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    for k, v in {**SECURITY_HEADERS, **(extra or {})}.items():
        headers.append((k.encode(), v.encode()))
    return status, headers, body


class SecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str,
        allowed_hosts: Iterable[str],
        allowed_origins: Iterable[str],
        limiter: RateLimiter,
        max_body_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.app = app
        self._token = token
        self._hosts = frozenset(h.lower() for h in allowed_hosts)
        self._origins = frozenset(allowed_origins)
        self._limiter = limiter
        self._max_body = max_body_bytes

    async def _respond(
        self, send: Send, status: int, code: str, message: str, extra: dict[str, str] | None = None
    ) -> None:
        status, headers, body = _error(status, code, message, extra)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            # No websocket surface exists; refuse rather than silently bypass the checks.
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return

        headers = Headers(scope=scope)
        host = (headers.get("host") or "").lower()
        if host not in self._hosts:
            await self._respond(send, 403, "forbidden_host", "Host header not allowed.")
            return
        origin = headers.get("origin")
        if origin is not None and origin not in self._origins:
            await self._respond(send, 403, "forbidden_origin", "Origin not allowed.")
            return

        path: str = scope["path"]
        method: str = scope["method"]

        if method != "OPTIONS" and path not in PUBLIC_PATHS:
            auth = headers.get("authorization", "")
            scheme, _, supplied = auth.partition(" ")
            if scheme.lower() != "bearer" or not constant_time_equals(supplied.strip(), self._token):
                await self._respond(
                    send,
                    401,
                    "unauthorized",
                    "Missing or invalid API token.",
                    {"www-authenticate": "Bearer"},
                )
                return

        if method != "OPTIONS" and not path.startswith(RATE_EXEMPT_PREFIXES):
            wait = self._limiter.check(self._limiter.classify(method, path))
            if wait > 0:
                await self._respond(
                    send,
                    429,
                    "rate_limited",
                    "Too many requests.",
                    {"retry-after": str(max(1, math.ceil(wait)))},
                )
                return

        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_body:
            await self._respond(send, 413, "payload_too_large", "Request body too large.")
            return

        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_body:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        started = False

        async def hardened_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                mutable = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    if k == "cache-control" and "cache-control" in mutable:
                        continue  # SSE sets its own no-cache
                    mutable[k] = v
            await send(message)

        await self.app(scope, limited_receive, hardened_send)
        if too_large and not started:
            await self._respond(send, 413, "payload_too_large", "Request body too large.")
