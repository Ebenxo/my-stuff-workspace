from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.core.secrets import MemorySecretStore
from app.repositories.events import EventFilter
from tests.conftest import Upstream

ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"


def models_ok(*ids: str) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": i} for i in ids]})


async def create_anthropic(client: httpx.AsyncClient, **over: object) -> dict:  # type: ignore[type-arg]
    body = {"kind": "anthropic", "name": "Claude", "api_key": ANTHROPIC_KEY, **over}
    r = await client.post("/api/providers", json=body)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_kinds_include_all_supported_backends(client: httpx.AsyncClient) -> None:
    kinds = {k["kind"]: k for k in (await client.get("/api/providers/kinds")).json()}
    assert {"anthropic", "openai", "gemini", "ollama", "lmstudio", "openai_compatible", "demo"} <= set(kinds)
    assert kinds["anthropic"]["needs_key"] and not kinds["ollama"]["needs_key"]
    assert kinds["ollama"]["local"] and kinds["ollama"]["default_base_url"].startswith("http://127.0.0.1")


async def test_key_is_write_only_everywhere(
    client: httpx.AsyncClient,
    app: FastAPI,
    secret_store: MemorySecretStore,
    caplog: pytest.LogCaptureFixture,
    upstream: Upstream,
) -> None:
    caplog.set_level(logging.DEBUG)
    upstream.on("api.anthropic.com", lambda r: models_ok("claude-sonnet-5-5"))
    p = await create_anthropic(client)
    assert p["has_key"] is True
    assert p["key_hint"] == "••••0123"
    await client.post(f"/api/providers/{p['id']}/test")
    await client.patch(f"/api/providers/{p['id']}", json={"name": "Renamed"})
    listing = (await client.get("/api/providers")).text
    assert ANTHROPIC_KEY not in listing and ANTHROPIC_KEY not in json.dumps(p)

    # It is in the secret store, under a reference stored on the row...
    assert await secret_store.get(f"provider:{p['id']}") == ANTHROPIC_KEY
    # ...and nowhere in the database or the audit log.
    db = app.state.container.db
    async with db.session() as s:
        dump = json.dumps(
            [dict(r._mapping) for r in (await s.execute(text("SELECT * FROM providers"))).all()], default=str
        )
        events = json.dumps(
            [dict(r._mapping) for r in (await s.execute(text("SELECT payload FROM events"))).all()],
            default=str,
        )
    assert ANTHROPIC_KEY not in dump and ANTHROPIC_KEY not in events
    assert "provider:" in dump
    # ...and not in any log line.
    assert all(ANTHROPIC_KEY not in rec.getMessage() for rec in caplog.records)
    # The key reached the upstream only in the header.
    sent = next(r for r in upstream.requests if r.url.path == "/v1/models")
    assert sent.headers["x-api-key"] == ANTHROPIC_KEY and ANTHROPIC_KEY not in str(sent.url)


async def test_cloud_kinds_require_a_key(client: httpx.AsyncClient) -> None:
    for kind in ("anthropic", "openai", "gemini"):
        r = await client.post("/api/providers", json={"kind": kind, "name": "x"})
        assert r.status_code == 422 and "API key" in r.json()["error"]["message"]
        r = await client.post("/api/providers", json={"kind": kind, "name": "x", "api_key": "   "})
        assert r.status_code == 422


async def test_local_kinds_need_no_key_and_custom_needs_url(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/providers", json={"kind": "ollama", "name": "Local"})
    assert r.status_code == 201 and r.json()["is_local"] and not r.json()["has_key"]
    r = await client.post("/api/providers", json={"kind": "openai_compatible", "name": "Custom"})
    assert r.status_code == 422 and "base URL" in r.json()["error"]["message"]
    r = await client.post(
        "/api/providers",
        json={"kind": "openai_compatible", "name": "Custom", "base_url": "https://gw.example.com/v1"},
    )
    assert r.status_code == 201 and not r.json()["is_local"]


@pytest.mark.parametrize(
    ("url", "key", "ok"),
    [
        ("https://gw.example.com/v1", "k" * 20, True),
        ("http://127.0.0.1:1234/v1", "k" * 20, True),  # loopback: cleartext never leaves the machine
        ("http://localhost:1234/v1", "k" * 20, True),
        ("http://192.168.1.5:1234/v1", None, True),  # LAN without a key is the user's call
        ("http://gw.example.com/v1", "k" * 20, False),  # key over cleartext
        ("ftp://gw.example.com", None, False),
        ("javascript:alert(1)", None, False),
        ("https://user:pass@gw.example.com/v1", None, False),
        ("https://gw.example.com/v1?token=abc", None, False),
        ("not a url", None, False),
    ],
)
async def test_base_url_validation(client: httpx.AsyncClient, url: str, key: str | None, ok: bool) -> None:
    body: dict[str, object] = {"kind": "openai_compatible", "name": "c", "base_url": url}
    if key:
        body["api_key"] = key
    r = await client.post("/api/providers", json=body)
    assert (r.status_code == 201) is ok, r.text


async def test_key_rotation_removal_and_cleartext_guard_on_update(
    client: httpx.AsyncClient, secret_store: MemorySecretStore
) -> None:
    p = (
        await client.post(
            "/api/providers",
            json={"kind": "openai_compatible", "name": "c", "base_url": "http://gw.example.com/v1"},
        )
    ).json()
    r = await client.patch(f"/api/providers/{p['id']}", json={"api_key": "k" * 20})
    assert r.status_code == 422  # adding a key to a cleartext remote endpoint is refused
    await client.patch(f"/api/providers/{p['id']}", json={"base_url": "https://gw.example.com/v1"})
    r = await client.patch(f"/api/providers/{p['id']}", json={"api_key": "new-key-0123456789"})
    assert r.json()["has_key"] and await secret_store.get(f"provider:{p['id']}") == "new-key-0123456789"
    r = await client.patch(f"/api/providers/{p['id']}", json={"name": "only-rename"})
    assert r.json()["has_key"]  # leaving api_key out keeps the stored key
    r = await client.patch(f"/api/providers/{p['id']}", json={"api_key": ""})
    assert not r.json()["has_key"] and await secret_store.get(f"provider:{p['id']}") is None


async def test_delete_removes_row_and_secret(
    client: httpx.AsyncClient, secret_store: MemorySecretStore
) -> None:
    p = await create_anthropic(client)
    assert (await client.delete(f"/api/providers/{p['id']}")).status_code == 204
    assert await secret_store.get(f"provider:{p['id']}") is None
    assert (await client.get("/api/providers")).json() == []
    assert (await client.delete(f"/api/providers/{p['id']}")).status_code == 404


async def test_connection_test_success_and_failure_are_recorded(
    client: httpx.AsyncClient, upstream: Upstream
) -> None:
    p = await create_anthropic(client)
    upstream.on("api.anthropic.com", lambda r: models_ok("claude-a", "claude-b"))
    ok = (await client.post(f"/api/providers/{p['id']}/test")).json()
    assert ok["ok"] and ok["models_found"] == 2 and ok["latency_ms"] >= 0
    got = (await client.get(f"/api/providers/{p['id']}")).json()
    assert got["last_test_ok"] is True and got["last_test_error"] is None and got["last_test_at"]

    upstream.on(
        "api.anthropic.com",
        lambda r: httpx.Response(401, json={"error": {"message": f"invalid key {ANTHROPIC_KEY}"}}),
    )
    bad = (await client.post(f"/api/providers/{p['id']}/test")).json()
    assert not bad["ok"] and bad["error_code"] == "auth_failed"
    assert ANTHROPIC_KEY not in json.dumps(bad)
    got = (await client.get(f"/api/providers/{p['id']}")).json()
    assert got["last_test_ok"] is False and ANTHROPIC_KEY not in (got["last_test_error"] or "")
    assert (await client.post("/api/providers/nope/test")).status_code == 404


async def test_unreachable_endpoint_reports_a_helpful_error(
    client: httpx.AsyncClient, upstream: Upstream
) -> None:
    p = (await client.post("/api/providers", json={"kind": "ollama", "name": "Local"})).json()

    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    upstream.on("127.0.0.1", refuse)
    result = (await client.post(f"/api/providers/{p['id']}/test")).json()
    assert not result["ok"] and "Is it running" in result["detail"] and result["error_code"] == "unavailable"


async def test_models_endpoints_add_default_model_and_aggregate(
    client: httpx.AsyncClient, upstream: Upstream
) -> None:
    upstream.on("api.anthropic.com", lambda r: models_ok("claude-haiku-x", "claude-opus-x"))
    upstream.on("127.0.0.1", lambda r: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    a = await create_anthropic(client, default_model="claude-not-listed")
    o = (await client.post("/api/providers", json={"kind": "ollama", "name": "Local"})).json()
    models = (await client.get(f"/api/providers/{a['id']}/models")).json()
    by_id = {m["id"]: m for m in models}
    assert set(by_id) == {"claude-haiku-x", "claude-opus-x", "claude-not-listed"}
    assert by_id["claude-haiku-x"]["tier"] == "fast" and by_id["claude-opus-x"]["tier"] == "strong"
    assert by_id["claude-haiku-x"]["input_cost_per_mtok"] is None  # unknown price is never guessed
    assert by_id["claude-haiku-x"]["ref"] == f"{a['id']}:claude-haiku-x"

    everything = (await client.get("/api/models")).json()
    local = next(m for m in everything if m["provider_id"] == o["id"])
    assert local["local"] and local["input_cost_per_mtok"] == 0.0

    calls = len(upstream.requests)
    await client.get(f"/api/providers/{a['id']}/models")
    assert len(upstream.requests) == calls  # served from cache
    await client.get(f"/api/providers/{a['id']}/models", params={"refresh": True})
    assert len(upstream.requests) == calls + 1
    assert (await client.get("/api/providers/nope/models")).status_code == 404


async def test_price_override_from_options_is_used(client: httpx.AsyncClient, upstream: Upstream) -> None:
    upstream.on("api.anthropic.com", lambda r: models_ok("claude-x"))
    p = await create_anthropic(
        client,
        options={
            "models": {
                "claude-x": {
                    "price": {"input": 3.0, "output": 15.0},
                    "tier": "strong",
                    "context_length": 200000,
                }
            }
        },
    )
    m = (await client.get(f"/api/providers/{p['id']}/models")).json()[0]
    assert (m["input_cost_per_mtok"], m["output_cost_per_mtok"], m["tier"], m["context_length"]) == (
        3.0,
        15.0,
        "strong",
        200000,
    )


async def test_provider_events_and_health(
    client: httpx.AsyncClient, app: FastAPI, upstream: Upstream
) -> None:
    health = {c["name"]: c for c in (await client.get("/api/health")).json()["checks"]}
    assert health["providers"]["status"] == "unavailable"

    upstream.on("api.anthropic.com", lambda r: models_ok("m"))
    p = await create_anthropic(client)
    health = {c["name"]: c for c in (await client.get("/api/health")).json()["checks"]}
    assert health["providers"]["status"] == "ok" and "not yet tested" in health["providers"]["detail"]

    upstream.on("api.anthropic.com", lambda r: httpx.Response(401, json={"error": {"message": "no"}}))
    await client.post(f"/api/providers/{p['id']}/test")
    health = {c["name"]: c for c in (await client.get("/api/health")).json()["checks"]}
    assert health["providers"]["status"] == "degraded"
    await client.delete(f"/api/providers/{p['id']}")

    types = [
        e.type
        for e in await app.state.container.bus.query(
            EventFilter(types=frozenset({"PROVIDER_CONFIGURED", "PROVIDER_TESTED", "PROVIDER_REMOVED"}))
        )
    ]
    assert types == ["PROVIDER_CONFIGURED", "PROVIDER_TESTED", "PROVIDER_REMOVED"]
    assert (await client.get("/api/events/verify")).json()["ok"] is True


async def test_budgets_roundtrip_and_validation(client: httpx.AsyncClient) -> None:
    default = (await client.get("/api/budgets")).json()
    assert (
        default["daily_usd"] is None and default["hard_stop"] is True and default["warn_at_fraction"] == 0.8
    )
    body = {
        **default,
        "daily_usd": 5,
        "monthly_usd": 50,
        "per_project_monthly_usd": {"proj_1": 10},
        "hard_stop": False,
    }
    assert (await client.put("/api/budgets", json=body)).status_code == 200
    got = (await client.get("/api/budgets")).json()
    assert (
        got["daily_usd"] == 5
        and got["per_project_monthly_usd"] == {"proj_1": 10}
        and got["hard_stop"] is False
    )
    assert (await client.put("/api/budgets", json={**body, "daily_usd": -1})).status_code == 422
    assert (await client.put("/api/budgets", json={**body, "warn_at_fraction": 0})).status_code == 422
    assert (await client.put("/api/budgets", json={**body, "surprise": 1})).status_code == 422


async def test_routing_rules_roundtrip_and_preview(client: httpx.AsyncClient, upstream: Upstream) -> None:
    upstream.on("api.anthropic.com", lambda r: models_ok("claude-haiku-x", "claude-opus-x"))
    upstream.on("127.0.0.1", lambda r: httpx.Response(200, json={"models": [{"name": "llama3:8b"}]}))
    a = await create_anthropic(client)
    o = (await client.post("/api/providers", json={"kind": "ollama", "name": "Local"})).json()

    preview = (await client.post("/api/routing/preview", json={"task_class": "coding"})).json()
    assert preview["primary"] == f"{a['id']}:claude-opus-x" and "default policy" in preview["reason"]

    rules = {
        "rules": [
            {"name": "private stays home", "when": {"private": True}, "prefer": {"provider_id": o["id"]}}
        ]
    }
    assert (await client.put("/api/routing/rules", json=rules)).status_code == 200
    assert (await client.get("/api/routing/rules")).json() == rules | {
        "rules": [
            {
                **rules["rules"][0],
                "when": {"task_class": None, "private": True, "min_input_tokens": None},
                "prefer": {"model": None, "provider_id": o["id"], "tier": None, "local": None},
            }
        ]
    }
    private = (
        await client.post("/api/routing/preview", json={"task_class": "coding", "private": True})
    ).json()
    assert private["primary"] == f"{o['id']}:llama3:8b"

    bad = {"rules": [{"name": "x", "when": {"task_class": "nonsense"}, "prefer": {"tier": "fast"}}]}
    assert (await client.put("/api/routing/rules", json=bad)).status_code == 422

    await client.delete(f"/api/providers/{o['id']}")
    refused = await client.post("/api/routing/preview", json={"private": True})
    assert refused.status_code == 409
    assert (
        refused.json()["error"]["code"] == "no_route" and "local model" in refused.json()["error"]["message"]
    )


@pytest.mark.parametrize(
    ("kind", "host", "path_suffix"),
    [("lmstudio", "127.0.0.1", "/v1/models"), ("ollama", "127.0.0.1", "/api/tags")],
)
async def test_local_kinds_really_call_their_documented_default_address(
    client: httpx.AsyncClient, upstream: Upstream, kind: str, host: str, path_suffix: str
) -> None:
    """Regression: LM Studio without a base URL used to fall through to api.openai.com."""
    upstream.on(host, lambda r: httpx.Response(200, json={"data": [{"id": "m"}], "models": [{"name": "m"}]}))
    p = (await client.post("/api/providers", json={"kind": kind, "name": "Local"})).json()
    result = (await client.post(f"/api/providers/{p['id']}/test")).json()
    assert result["ok"], result
    assert [r.url.host for r in upstream.requests] == [host]
    assert upstream.requests[0].url.path == path_suffix
    kinds = {k["kind"]: k for k in (await client.get("/api/providers/kinds")).json()}
    assert kinds[kind]["default_base_url"].startswith(f"http://{host}")  # what the UI shows is what is called


async def test_every_cloud_kind_targets_its_own_vendor_by_default(
    client: httpx.AsyncClient, upstream: Upstream
) -> None:
    hosts = {
        "anthropic": "api.anthropic.com",
        "openai": "api.openai.com",
        "gemini": "generativelanguage.googleapis.com",
    }
    for kind, host in hosts.items():
        upstream.on(host, lambda r: httpx.Response(200, json={"data": [], "models": []}))
        p = (
            await client.post("/api/providers", json={"kind": kind, "name": kind, "api_key": "k" * 24})
        ).json()
        await client.post(f"/api/providers/{p['id']}/test")
    assert [r.url.host for r in upstream.requests] == list(hosts.values())
