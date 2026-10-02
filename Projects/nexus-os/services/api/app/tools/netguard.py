"""SafeHttpClient: the only egress path for agent tools.

Defends against SSRF: only http(s); refuses private, loopback, link-local, metadata, multicast and
reserved addresses (IPv4, IPv6, IPv4-mapped/6to4/NAT64 forms, and odd numeric host encodings, because
we validate what DNS *resolves to*, not how the host is spelled); connects to the validated IP so DNS
cannot change between check and use; re-validates every redirect hop; caps size, time and redirects;
refuses binary content; never sends credentials to a different host after a redirect.

Behind a system proxy the proxy resolves names, so pinning is impossible: the client then runs in
"proxied" mode (host-name and literal-IP checks plus any local DNS answer) and says so in its result.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import urllib.request
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlsplit

import httpx

BLOCKED_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".home.arpa",
    ".intranet",
    ".corp",
    ".private",
)
BLOCKED_NAMES = frozenset({"localhost", "metadata", "metadata.google.internal", "instance-data"})
TEXTUAL = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml",
    "application/javascript",
    "application/x-yaml",
    "application/yaml",
    "application/rss",
    "application/atom",
    "application/ld+json",
)
STRIP_ON_CROSS_HOST = ("authorization", "cookie", "proxy-authorization", "x-api-key")
FORBIDDEN_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "connection", "transfer-encoding", "upgrade", "te", "trailer"}
)

Resolver = Callable[[str, int], Awaitable[list[str]]]


class NetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_blocked_ip(value: str) -> bool:
    """True for anything that is not a normal public internet address."""
    try:
        ip = ipaddress.ip_address(value.strip("[]").split("%", 1)[0])
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or (ip.sixtofour if ip.sixtofour else None)
        if embedded is None and ip in ipaddress.ip_network("64:ff9b::/96"):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is None and ip.teredo:
            embedded = ip.teredo[1]
        if embedded is not None:
            return is_blocked_ip(str(embedded))
    return not ip.is_global or ip.is_multicast or ip.is_unspecified


def host_looks_internal(host: str) -> bool:
    h = host.lower().rstrip(".")
    return h in BLOCKED_NAMES or h.endswith(BLOCKED_SUFFIXES) or ("." not in h and not _is_ip(h))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(i[4][0]) for i in infos))


def system_uses_proxy() -> bool:
    return any(k.lower() in ("http", "https", "all") for k in urllib.request.getproxies())


@dataclass
class HttpResult:
    status: int
    final_url: str
    content_type: str
    text: str
    truncated: bool
    redirects: list[str] = field(default_factory=list)
    ssrf_mode: str = "pinned"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str
    port: int
    ips: list[str]


_TAGS = re.compile(r"<(script|style|noscript|template|svg)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_ANY_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n\s*\n+")


def html_to_text(html: str) -> str:
    """Readable text from HTML (scripts, styles and comments dropped) to save tokens."""
    text = _COMMENTS.sub("", _TAGS.sub("", html))
    text = re.sub(r"</(p|div|li|tr|h[1-6]|br|section|article)\s*>|<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = unescape(_ANY_TAG.sub("", text))
    return _NL.sub("\n\n", _WS.sub(" ", text)).strip()


class SafeHttpClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = system_resolver,
        proxied: bool | None = None,
        max_redirects: int = 3,
    ) -> None:
        self._transport = transport
        self._resolver = resolver
        self._proxied = system_uses_proxy() if proxied is None else proxied
        self._max_redirects = max_redirects

    async def validate(
        self, url: str, *, allow_private: Iterable[str] = (), allowed_domains: Iterable[str] = ()
    ) -> Target:
        try:
            parsed = urlsplit(url.strip())
            port = parsed.port
        except ValueError:
            raise NetError("invalid_url", "That is not a valid URL.") from None
        if parsed.scheme not in ("http", "https"):
            raise NetError("invalid_url", "Only http:// and https:// URLs are allowed.")
        if not parsed.hostname:
            raise NetError("invalid_url", "The URL has no host.")
        if parsed.username or parsed.password:
            raise NetError("invalid_url", "URLs with embedded credentials are not allowed.")
        host = parsed.hostname.lower().rstrip(".")
        port = port or (443 if parsed.scheme == "https" else 80)
        domains = [d.lower().lstrip(".") for d in allowed_domains]
        if domains and not any(host == d or host.endswith("." + d) for d in domains):
            raise NetError("domain_not_allowed", f"{host} is not on this project's allowed-domain list.")
        exempt = {a.lower() for a in allow_private}
        if host in exempt or f"{host}:{port}" in exempt:
            return Target(
                parsed.scheme, host, port, [host] if _is_ip(host) else await self._resolver(host, port)
            )
        if _is_ip(host):
            if is_blocked_ip(host):
                raise NetError(
                    "blocked_address", f"{host} is a private or reserved address and cannot be reached."
                )
            return Target(parsed.scheme, host, port, [host])
        if host_looks_internal(host):
            raise NetError("blocked_address", f"{host} looks like an internal name and cannot be reached.")
        try:
            ips = await self._resolver(host, port)
        except (OSError, UnicodeError):
            if self._proxied:
                return Target(parsed.scheme, host, port, [])  # the proxy resolves names
            raise NetError("dns_failed", f"Could not resolve {host}.") from None
        if any(is_blocked_ip(i) for i in ips):
            raise NetError(
                "blocked_address", f"{host} resolves to a private or reserved address and cannot be reached."
            )
        return Target(parsed.scheme, host, port, ips)

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: str | bytes | None = None,
        timeout_s: float = 20.0,
        max_bytes: int = 1_000_000,
        allow_private: Iterable[str] = (),
        allowed_domains: Iterable[str] = (),
        as_text: bool = True,
    ) -> HttpResult:
        method = method.upper()
        data = body.encode("utf-8") if isinstance(body, str) else body
        if data is not None and len(data) > 1_000_000:
            raise NetError("too_large", "The request body is larger than 1 MB.")
        hdrs = {k: v for k, v in (headers or {}).items() if k.lower() not in FORBIDDEN_REQUEST_HEADERS}
        redirects: list[str] = []
        current = url
        origin_host = (urlsplit(url).hostname or "").lower()
        try:
            async with asyncio.timeout(timeout_s):
                for _hop in range(self._max_redirects + 1):
                    target = await self.validate(
                        current, allow_private=allow_private, allowed_domains=allowed_domains
                    )
                    if target.host != origin_host:
                        hdrs = {k: v for k, v in hdrs.items() if k.lower() not in STRIP_ON_CROSS_HOST}
                    response, _ = await self._send(method, current, target, hdrs, data)
                    try:
                        if (
                            response.status_code in (301, 302, 303, 307, 308)
                            and "location" in response.headers
                        ):
                            redirects.append(current)
                            current = urljoin(current, response.headers["location"])
                            if response.status_code in (301, 302, 303) and method != "HEAD":
                                method, data = "GET", None
                                hdrs = {k: v for k, v in hdrs.items() if k.lower() != "content-type"}
                            continue
                        return await self._read(
                            response,
                            current,
                            redirects,
                            max_bytes,
                            as_text,
                            "proxied" if self._proxied else "pinned",
                        )
                    finally:
                        await response.aclose()
                raise NetError("too_many_redirects", f"More than {self._max_redirects} redirects.")
        except TimeoutError:
            raise NetError("timeout", f"The request took longer than {timeout_s:g} seconds.") from None
        except httpx.HTTPError as exc:
            raise NetError("network_error", f"Network error: {type(exc).__name__}") from None

    async def _send(
        self, method: str, url: str, target: Target, hdrs: dict[str, str], data: bytes | None
    ) -> tuple[httpx.Response, str | None]:
        async def build_and_send(
            client: httpx.AsyncClient, request_url: str, extra_headers: dict[str, str], ext: dict[str, str]
        ) -> httpx.Response:
            req = client.build_request(
                method, request_url, headers={**hdrs, **extra_headers}, content=data, extensions=ext
            )
            return await client.send(req, stream=True)

        if self._proxied or not target.ips:
            client = httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                trust_env=self._transport is None,
                timeout=httpx.Timeout(10.0, read=30.0),
            )
            try:
                resp = await build_and_send(client, url, {}, {})
            except BaseException:
                await client.aclose()
                raise
            return _Owned(resp, client), None  # type: ignore[return-value]

        last: Exception | None = None
        for ip in target.ips:
            client = httpx.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(10.0, read=30.0),
            )
            pinned = httpx.URL(url).copy_with(host=ip)
            host_header = target.host if target.port in (80, 443) else f"{target.host}:{target.port}"
            try:
                resp = await build_and_send(
                    client, str(pinned), {"Host": host_header}, {"sni_hostname": target.host}
                )
                return _Owned(resp, client), ip  # type: ignore[return-value]
            except httpx.ConnectError as exc:
                last = exc
                await client.aclose()
            except BaseException:
                await client.aclose()
                raise
        raise NetError(
            "network_error",
            f"Could not connect to {target.host}: {type(last).__name__ if last else 'no address'}",
        )

    async def _read(
        self,
        response: httpx.Response,
        url: str,
        redirects: list[str],
        max_bytes: int,
        as_text: bool,
        mode: str,
    ) -> HttpResult:
        ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype and not (ctype.startswith(TEXTUAL) or ctype.endswith(("+json", "+xml"))):
            raise NetError("binary_content", f"The response is {ctype}, which is not readable as text.")
        declared = response.headers.get("content-length")
        chunks: list[bytes] = []
        total = 0
        truncated = bool(declared and declared.isdigit() and int(declared) > max_bytes * 8)
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                chunks.append(chunk[: max(0, max_bytes - (total - len(chunk)))])
                truncated = True
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        if not ctype and b"\x00" in raw[:4096]:
            raise NetError("binary_content", "The response looks binary and cannot be read as text.")
        charset = "utf-8"
        m = re.search(r"charset=([\w-]+)", response.headers.get("content-type", ""), re.IGNORECASE)
        if m:
            charset = m.group(1)
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        if as_text and ctype in ("text/html", "application/xhtml+xml"):
            text = html_to_text(text)
        return HttpResult(
            status=response.status_code,
            final_url=url,
            content_type=ctype,
            text=text,
            truncated=truncated,
            redirects=redirects,
            ssrf_mode=mode,
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower() in ("content-type", "content-length", "last-modified", "etag", "date")
            },
        )


class _Owned:
    """Wraps a streamed response so closing it also closes the one-shot client that produced it."""

    def __init__(self, response: httpx.Response, client: httpx.AsyncClient) -> None:
        self._r = response
        self._c = client

    def __getattr__(self, name: str) -> object:
        return getattr(self._r, name)

    async def aclose(self) -> None:
        await self._r.aclose()
        await self._c.aclose()
