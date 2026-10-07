"""Adapters against a real HTTP server on loopback (no mock transport): chunked SSE, auth, redirects."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.providers.errors import ProviderAuthError, ProviderBadRequest
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.registry import new_http_client
from app.providers.types import ChatMessage, GenerateRequest
from tests.providers_helpers import Answer

SECRET = "local-secret-key-0123456789"


class Handler(BaseHTTPRequestHandler):
    seen: list[dict[str, object]] = []
    redirect_to: str | None = None

    def log_message(self, *a: object) -> None:  # silence
        pass

    def _json(self, status: int, body: object) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        type(self).seen.append({"path": self.path, "auth": self.headers.get("authorization")})
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("location", type(self).redirect_to or "/")
            self.end_headers()
            return
        if self.headers.get("authorization") != f"Bearer {SECRET}":
            return self._json(401, {"error": {"message": "bad key"}})
        if self.path.endswith("/models"):
            return self._json(200, {"data": [{"id": "local-model"}]})
        self._json(404, {"error": {"message": "nope"}})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
        if self.headers.get("authorization") != f"Bearer {SECRET}":
            return self._json(401, {"error": {"message": "bad key"}})
        if body.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            frames = [
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {"content": "lo "}}]},
                {"choices": [{"delta": {"content": "world"}}]},
                {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
            ]
            payload = "".join(f"data: {json.dumps(f)}\n\n" for f in frames) + "data: [DONE]\n\n"
            # Deliberately split mid-frame to prove the reader reassembles chunks.
            data = payload.encode()
            for i in range(0, len(data), 13):
                piece = data[i : i + 13]
                self.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            return
        fmt = body.get("response_format")
        if fmt and fmt.get("type") == "json_schema":
            content = json.dumps({"city": "Lyon", "population_millions": 0.5})
        else:
            content = "plain reply"
        self._json(
            200,
            {
                "model": body["model"],
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )


def serve() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def local() -> Iterator[str]:
    Handler.seen = []
    Handler.redirect_to = None
    server, url = serve()
    yield url
    server.shutdown()


def req() -> GenerateRequest:
    return GenerateRequest(model="local-model", messages=[ChatMessage(role="user", content="hi")])


async def test_generate_stream_structured_and_models_over_real_sockets(local: str) -> None:
    async with new_http_client() as http:
        p = OpenAICompatProvider("p", http, kind="lmstudio", api_key=SECRET, base_url=f"{local}/v1")
        assert (await p.generate(req())).text == "plain reply"
        chunks = [c async for c in p.stream(req())]
        assert "".join(c.text for c in chunks if c.kind == "text") == "Hello world"
        usage = next(c.usage for c in chunks if c.kind == "usage")
        assert usage is not None and (usage.input_tokens, usage.output_tokens) == (7, 3)
        structured = await p.generate_structured(req(), Answer)
        assert structured.value == Answer(city="Lyon", population_millions=0.5)
        assert [m.id for m in await p.available_models()] == ["local-model"]
        test = await p.test_connection()
        assert test.ok and test.models_found == 1


async def test_wrong_key_is_an_auth_error_over_the_wire(local: str) -> None:
    async with new_http_client() as http:
        p = OpenAICompatProvider("p", http, kind="lmstudio", api_key="wrong", base_url=f"{local}/v1")
        with pytest.raises(ProviderAuthError):
            await p.generate(req())
        result = await p.test_connection()
        assert not result.ok and result.error_code == "auth_failed"


async def test_redirects_are_refused_so_the_key_cannot_be_replayed_elsewhere(local: str) -> None:
    attacker, attacker_url = serve()
    try:
        Handler.seen = []
        Handler.redirect_to = f"{attacker_url}/steal"
        async with new_http_client() as http:
            p = OpenAICompatProvider(
                "p", http, kind="openai_compatible", api_key=SECRET, base_url=f"{local}/redirect"
            )
            with pytest.raises(ProviderBadRequest):  # a 3xx is an error, not something to follow
                await p.available_models()
        # Both "servers" are the same Handler class here, so check by path: nothing reached /steal.
        assert not any(str(s["path"]).startswith("/steal") for s in Handler.seen)
    finally:
        attacker.shutdown()


async def test_loopback_endpoints_bypass_system_proxies(local: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Local model servers work even with a (dead) proxy configured and NO_PROXY unset."""
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(var, raising=False)
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:9")  # nothing listens here
    async with new_http_client() as http:
        p = OpenAICompatProvider("p", http, kind="lmstudio", api_key=SECRET, base_url=f"{local}/v1")
        assert (await p.generate(req())).text == "plain reply"
