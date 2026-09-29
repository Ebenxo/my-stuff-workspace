from __future__ import annotations

import httpx

from app.api.ratelimit import RateLimiter
from app.core.secrets import MemorySecretStore
from app.core.settings import Settings
from app.main import create_app
from tests.conftest import TOKEN


async def test_ping_is_public_and_minimal(anon_client: httpx.AsyncClient) -> None:
    r = await anon_client.get("/api/health/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_missing_and_wrong_token_rejected(anon_client: httpx.AsyncClient) -> None:
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": f"Basic {TOKEN}"}):
        r = await anon_client.get("/api/projects", headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"
        assert r.headers["www-authenticate"] == "Bearer"


async def test_valid_token_accepted(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/projects")).status_code == 200


async def test_no_trailing_slash_redirects(client: httpx.AsyncClient) -> None:
    # A redirect names the API's own origin; a browser behind the dev proxy would follow it without
    # its token (found live: "/api/projects/" answered 307 -> 401). A wrong path is simply a 404.
    r = await client.get("/api/projects/")
    assert r.status_code == 404 and "location" not in r.headers


async def test_dns_rebinding_host_rejected(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/projects", headers={"Host": "evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_host"


async def test_ping_also_checks_host(anon_client: httpx.AsyncClient) -> None:
    r = await anon_client.get("/api/health/ping", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


async def test_foreign_origin_rejected_even_with_token(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/projects", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_origin"


async def test_allowed_origin_gets_cors_headers(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/projects", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_preflight_from_allowed_origin_works_without_token(
    anon_client: httpx.AsyncClient,
) -> None:
    r = await anon_client.options(
        "/api/projects",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert r.status_code == 200
    assert "authorization" in r.headers["access-control-allow-headers"].lower()


async def test_preflight_from_foreign_origin_gets_no_allowance(
    anon_client: httpx.AsyncClient,
) -> None:
    r = await anon_client.options(
        "/api/projects",
        headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/projects")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


async def test_body_size_limit(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/projects",
        content=b"x" * (3 * 1024 * 1024),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413


async def test_errors_use_envelope_without_leaking(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/projects/proj_missing")
    assert r.status_code == 404
    body = r.json()["error"]
    assert body["code"] == "not_found"
    r = await client.post("/api/projects", json={"name": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_docs_ui_is_disabled(client: httpx.AsyncClient) -> None:
    assert (await client.get("/docs")).status_code == 404


async def test_rate_limit_returns_429(tmp_path, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    limited = settings.model_copy(update={"rate_limit_enabled": True})
    app = create_app(limited, secrets=MemorySecretStore())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=f"http://127.0.0.1:{limited.port}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        ) as c,
    ):
        codes = [(await c.get("/api/projects")).status_code for _ in range(140)]
    assert 429 in codes
    assert codes[0] == 200


def test_rate_limiter_refills() -> None:
    now = [0.0]
    rl = RateLimiter(True, clock=lambda: now[0])
    for _ in range(20):
        assert rl.check("sensitive") == 0
    assert rl.check("sensitive") > 0
    now[0] += 5.0
    assert rl.check("sensitive") == 0


def test_rate_limit_classification() -> None:
    assert RateLimiter.classify("GET", "/api/projects") == "read"
    assert RateLimiter.classify("POST", "/api/projects") == "write"
    assert RateLimiter.classify("POST", "/api/approvals/appr_1/decision") == "sensitive"
    assert RateLimiter.classify("POST", "/api/providers/prov_1/test") == "sensitive"
    assert RateLimiter.classify("POST", "/api/objectives") == "sensitive"
