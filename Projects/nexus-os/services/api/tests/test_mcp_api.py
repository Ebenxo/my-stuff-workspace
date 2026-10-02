"""MCP servers through the API: configuration and write-only secrets, discovery into the tool registry,
calls through the executor (risk, approvals, taint, private runs), definition changes, crashes, HTTP."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.risk import RiskLevel
from app.core.secrets import MemorySecretStore
from app.core.settings import Settings
from app.permissions.taint import TaintTracker
from app.schemas.common import PermissionLevel
from app.services.container import AppContainer
from tests.runtime_helpers import make_rt

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_server.py"
sys.path.insert(0, str(FIXTURE.parent))
import mcp_server  # noqa: E402

TOKEN_VALUE = "fixture-token-value-7781"


def stdio_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "fixture",
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(FIXTURE)],
        "env": {"PLAIN_SETTING": "1"},
        "secret_env": {"FIXTURE_TOKEN": TOKEN_VALUE},
    }
    body.update(over)
    return body


async def add(client: httpx.AsyncClient, **over: Any) -> dict[str, Any]:
    r = await client.post("/api/mcp/servers", json=stdio_body(**over))
    assert r.status_code == 201, r.text
    return r.json()


async def events_of(client: httpx.AsyncClient, type_: str) -> list[dict[str, Any]]:
    r = await client.get("/api/events", params={"limit": 500})
    return [e for e in r.json() if e["type"] == type_]


async def wait_for(predicate: Any, timeout_s: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met in time")


async def test_add_a_server_its_tools_join_the_registry(client: httpx.AsyncClient, app: FastAPI) -> None:
    server = await add(client)
    assert server["status"] == "running", server
    assert (server["tools"], server["resources"], server["prompts"]) == (11, 2, 1)
    assert (server["server_name"], server["protocol_version"]) == ("fixture", "2025-06-18")
    assert server["secret_env"] == ["FIXTURE_TOKEN"] and server["env"] == {"PLAIN_SETTING": "1"}

    tools = {t["name"]: t for t in (await client.get("/api/tools")).json()}
    echo = tools["mcp__fixture__echo"]
    assert echo["source"] == "mcp:fixture" and echo["risk_level"] == "HIGH"
    assert echo["capabilities"] == ["mcp"] and echo["available"] and echo["enabled"]
    assert "mcp__fixture__files_read" in tools  # "files.read" made a valid name

    detail = (await client.get(f"/api/mcp/servers/{server['id']}")).json()
    by_name = {t["original_name"]: t for t in detail["tools"]}
    assert by_name["echo"]["hints"] == ["The server says this tool only reads."]
    assert by_name["echo"]["input_schema"]["required"] == ["text"]
    assert detail["instructions"] == "Fixture server for NEXUS tests."
    assert [p["name"] for p in detail["prompts"]] == ["summarize"]
    assert detail["prompts"][0]["arguments"][0] == {
        "name": "topic",
        "description": "What to summarize",
        "required": True,
    }

    assert (await events_of(client, "MCP_SERVER_ADDED"))[0]["payload"]["name"] == "fixture"
    started = (await events_of(client, "MCP_SERVER_STARTED"))[0]["payload"]
    assert started["tools"] == 11
    log = (await client.get(f"/api/mcp/servers/{server['id']}/log")).json()["lines"]
    assert "fixture: started" in log


async def test_secret_values_are_write_only(
    client: httpx.AsyncClient, app: FastAPI, settings: Settings, secret_store: MemorySecretStore
) -> None:
    server = await add(client)
    c: AppContainer = app.state.container
    # The server received it...
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    out = await rt.call("mcp__fixture__secret", {})
    assert out.status == "ok" and out.text == f"token: set (length {len(TOKEN_VALUE)})"
    # ...but it is nowhere else: not in responses, the database or the event log.
    for path in ("/api/mcp/servers", f"/api/mcp/servers/{server['id']}", "/api/events?limit=500"):
        assert TOKEN_VALUE not in (await client.get(path)).text
    db = sqlite3.connect(settings.home / "nexus.db") if (settings.home / "nexus.db").exists() else None
    if db is not None:
        dump = "\n".join(db.iterdump())
        assert TOKEN_VALUE not in dump
        db.close()
    assert await secret_store.get(f"mcp:{server['id']}:env:fixture_token") == TOKEN_VALUE
    assert c is not None
    # Rotating it restarts the server with the new value; removing it is explicit.
    r = await client.patch(f"/api/mcp/servers/{server['id']}", json={"secret_env": {"FIXTURE_TOKEN": "abc"}})
    assert r.status_code == 200 and r.json()["status"] == "running"
    assert (await rt.call("mcp__fixture__secret", {})).text == "token: set (length 3)"
    r = await client.patch(f"/api/mcp/servers/{server['id']}", json={"secret_env": {"FIXTURE_TOKEN": None}})
    assert r.json()["secret_env"] == []
    assert await secret_store.get(f"mcp:{server['id']}:env:fixture_token") is None
    # Deleting the server deletes its secrets and its tools.
    await client.patch(f"/api/mcp/servers/{server['id']}", json={"secret_env": {"FIXTURE_TOKEN": "again"}})
    assert (await client.delete(f"/api/mcp/servers/{server['id']}")).status_code == 204
    assert await secret_store.get(f"mcp:{server['id']}:env:fixture_token") is None
    assert not any(t["source"] == "mcp:fixture" for t in (await client.get("/api/tools")).json())
    assert c.tools.get("mcp__fixture__echo") is None
    assert (await events_of(client, "MCP_SERVER_REMOVED"))[0]["payload"]["name"] == "fixture"


@pytest.mark.parametrize(
    ("over", "fragment"),
    [
        ({"env": {"GITHUB_TOKEN": "abc"}}, "looks like a credential"),
        ({"env": {"SETTING": "sk-ant-abcdefghijklmnopqrstuvwx"}}, "looks like a credential"),
        ({"args": ["--key", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"]}, "looks like a credential"),
        ({"env": {"A": "1"}, "secret_env": {"a": "2"}}, "set twice"),
        ({"command": ""}, "Give the command"),
        ({"cwd": "relative/folder"}, "full path"),
        ({"risk_level": "SAFE"}, "moderate"),
        ({"transport": "http", "url": "ftp://example.com"}, "http:// or https://"),
        ({"transport": "http", "url": "https://user:pw@example.com/mcp"}, "user name"),
        ({"transport": "http", "url": "https://example.com/mcp?token=abcdef123456"}, "token"),
        (
            {
                "transport": "http",
                "url": "http://example.com/mcp",
                "secret_headers": {"Authorization": "Bearer x"},
            },
            "unencrypted",
        ),
        (
            {"transport": "http", "url": "https://example.com/mcp", "headers": {"Authorization": "x"}},
            "credential",
        ),
    ],
)
async def test_configuration_is_checked(
    client: httpx.AsyncClient, over: dict[str, Any], fragment: str
) -> None:
    body = stdio_body(**over)
    if over.get("transport") == "http":
        body.pop("secret_env")
        body.pop("env")
    r = await client.post("/api/mcp/servers", json=body)
    assert r.status_code == 422, r.text
    assert fragment in r.json()["error"]["message"]


async def test_names_are_unique_and_well_formed(client: httpx.AsyncClient) -> None:
    await add(client, enabled=False)
    assert (await client.post("/api/mcp/servers", json=stdio_body())).status_code == 409
    assert (await client.post("/api/mcp/servers", json=stdio_body(name="Bad Name"))).status_code == 422
    assert (await client.post("/api/mcp/servers", json=stdio_body(name="a__b"))).status_code == 422


async def test_calls_go_through_policy_approvals_and_taint(client: httpx.AsyncClient, app: FastAPI) -> None:
    await add(client)
    rt = await make_rt(app, level=PermissionLevel.BALANCED)
    # HIGH at the balanced level: a person decides. The card says what will happen.
    outcome, approval = await rt.approved("mcp__fixture__echo", {"text": "hello"})
    assert approval.risk_level == RiskLevel.HIGH
    assert "MCP server “fixture”" in approval.impact and "only reads" in approval.impact
    assert outcome.status == "ok" and outcome.text == "echo: hello"
    assert outcome.untrusted and outcome.source == "mcp:fixture/echo"

    # Permissive: runs by itself, and the result taints the run...
    perm = await make_rt(app, level=PermissionLevel.PERMISSIVE, name="Permissive")
    taint = TaintTracker()
    ectx = await perm.ectx(taint=taint)
    first = await perm.call("mcp__fixture__add", {"a": 2, "b": 5}, ectx)
    assert first.status == "ok" and first.text == "7"
    assert "mcp:fixture/add" in taint.sources
    # ...so the next HIGH action waits for a person, even at the permissive level.
    task = asyncio.create_task(perm.call("mcp__fixture__add", {"a": 1, "b": 1}, ectx))
    pending = await perm.pending()
    assert pending.tainted and "mcp:fixture/add" in pending.taint_sources
    await perm.decide(pending, "deny")
    assert (await asyncio.wait_for(task, 10)).status == "denied"

    # Scheduled (unattended) runs never auto-approve it either.
    task = asyncio.create_task(
        perm.call("mcp__fixture__add", {"a": 1, "b": 1}, await perm.ectx(unattended=True))
    )
    await perm.decide(await perm.pending(), "deny")
    assert (await asyncio.wait_for(task, 10)).status == "denied"

    # Arguments are checked against the server's schema before anyone is asked.
    bad = await perm.call("mcp__fixture__echo", {"text": 5, "other": 1})
    assert (
        bad.status == "invalid"
        and "text: must be string" in bad.text
        and "other: not an accepted" in bad.text
    )

    # A tool error comes back as a failure the agent can read.
    failed = await perm.call("mcp__fixture__fail", {})
    assert failed.status == "failed" and failed.error_code == "mcp_tool_error" and "it broke" in failed.text


async def test_private_runs_and_low_ceiling_agents_cannot_use_mcp_tools(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    await add(client)
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    ectx = await rt.ectx()
    ectx.tool_context.private = True
    out = await rt.call("mcp__fixture__echo", {"text": "x"}, ectx)
    assert out.status == "denied" and out.error_code == "private_run"
    # An agent whose ceiling is MODERATE is refused outright: nobody is asked.
    low = await make_rt(app, level=PermissionLevel.PERMISSIVE, max_risk=RiskLevel.MODERATE, name="Low")
    out = await low.call("mcp__fixture__echo", {"text": "x"})
    assert out.status == "denied" and out.error_code == "policy_denied"
    # The risk level is the person's choice (not below moderate): at MODERATE a balanced project runs it.
    server = (await client.get("/api/mcp/servers")).json()[0]
    r = await client.patch(f"/api/mcp/servers/{server['id']}", json={"risk_level": "MODERATE"})
    assert r.json()["risk_level"] == "MODERATE" and r.json()["status"] == "running"
    balanced = await make_rt(app, level=PermissionLevel.BALANCED, name="Balanced")
    assert (await balanced.call("mcp__fixture__echo", {"text": "ok"})).text == "echo: ok"


async def test_stop_and_start_withdraw_and_restore_tools(client: httpx.AsyncClient, app: FastAPI) -> None:
    server = await add(client)
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    stopped = (await client.post(f"/api/mcp/servers/{server['id']}/stop")).json()
    assert stopped["status"] == "stopped" and not stopped["enabled"]
    tools = {t["name"]: t for t in (await client.get("/api/tools")).json()}
    assert tools["mcp__fixture__echo"]["available"] is False  # kept, with the person's choices
    out = await rt.call("mcp__fixture__echo", {"text": "x"})
    assert out.status == "denied" and out.error_code == "unknown_tool"
    # A choice can still be made while the server is stopped.
    r = await client.patch("/api/tools/mcp__fixture__add", json={"enabled": False})
    assert r.status_code == 200 and not r.json()["enabled"]
    started = (await client.post(f"/api/mcp/servers/{server['id']}/start")).json()
    assert started["status"] == "running" and started["enabled"]
    assert (await rt.call("mcp__fixture__echo", {"text": "back"})).text == "echo: back"
    assert (await rt.call("mcp__fixture__add", {"a": 1, "b": 2})).status == "denied"  # still switched off
    checked = (await client.post(f"/api/mcp/servers/{server['id']}/check")).json()
    assert checked["last_health"]["ok"] and checked["last_health"]["latency_ms"] is not None
    assert [e["payload"]["name"] for e in await events_of(client, "MCP_SERVER_STOPPED")] == ["fixture"]


async def test_a_crash_is_reported_and_its_tools_withdrawn(client: httpx.AsyncClient, app: FastAPI) -> None:
    server = await add(client)
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    out = await rt.call("mcp__fixture__crash", {})
    assert out.status == "failed" and "exit code 3" in out.text
    status = (await client.get(f"/api/mcp/servers/{server['id']}")).json()["server"]
    assert status["status"] == "error" and "exit code 3" in status["error"]
    c: AppContainer = app.state.container
    assert c.tools.get("mcp__fixture__echo") is None

    async def reported() -> bool:
        return bool(await events_of(client, "MCP_SERVER_FAILED"))

    await wait_for(reported)
    failed = await events_of(client, "MCP_SERVER_FAILED")
    assert "exit code 3" in failed[0]["payload"]["message"]
    health = (await client.get("/api/health")).json()
    mcp = next(ch for ch in health["checks"] if ch["name"] == "mcp")
    assert mcp["status"] == "degraded" and "fixture" in mcp["detail"]
    # Nothing restarts it silently; the person does.
    assert (await client.post(f"/api/mcp/servers/{server['id']}/start")).json()["status"] == "running"


async def test_changed_or_suspicious_definitions_are_switched_off(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    server = await add(client, env={"FIXTURE_POISON": "1"})
    tools = {t["name"]: t for t in (await client.get("/api/tools")).json()}
    helper = tools["mcp__fixture__helper"]
    assert not helper["enabled"] and "instructions to an AI" in helper["note"]
    assert tools["mcp__fixture__echo"]["enabled"]
    flags = await events_of(client, "SECURITY_FLAG")
    assert any(f["payload"]["tool"] == "mcp__fixture__helper" for f in flags)
    # A disabled tool is never shown to an agent's model, and cannot be called.
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    assert (await rt.call("mcp__fixture__helper", {})).status == "denied"

    # The server changes what "echo" says it does: switched off until the person looks again.
    r = await client.patch(
        f"/api/mcp/servers/{server['id']}", json={"env": {"FIXTURE_POISON": "1", "FIXTURE_VARIANT": "2"}}
    )
    assert r.json()["status"] == "running"
    tools = {t["name"]: t for t in (await client.get("/api/tools")).json()}
    assert not tools["mcp__fixture__echo"]["enabled"]
    assert "changed this tool" in tools["mcp__fixture__echo"]["note"]
    assert tools["mcp__fixture__echo"]["description"] == "Repeats the text back, louder."
    assert tools["mcp__fixture__add"]["enabled"]  # unchanged tools are untouched
    r = await client.patch("/api/tools/mcp__fixture__echo", json={"enabled": True})
    assert r.json()["enabled"] and r.json()["note"] is None


async def test_list_changes_are_picked_up(client: httpx.AsyncClient, app: FastAPI) -> None:
    await add(client)
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    assert (await rt.call("mcp__fixture__grow", {})).text == "grown"
    c: AppContainer = app.state.container

    async def grown() -> bool:
        return c.tools.get("mcp__fixture__extra") is not None

    await wait_for(grown)
    assert (await rt.call("mcp__fixture__extra", {})).text == "extra!"
    changed = await events_of(client, "MCP_TOOLS_CHANGED")
    assert changed and changed[0]["payload"]["added"] == ["mcp__fixture__extra"]


async def test_resources_and_prompts_can_be_previewed(client: httpx.AsyncClient) -> None:
    server = await add(client)
    base = f"/api/mcp/servers/{server['id']}"
    text = (await client.post(f"{base}/resources/read", json={"uri": "fixture://notes/hello"})).json()
    assert text == [
        {
            "uri": "fixture://notes/hello",
            "mime_type": "text/plain",
            "text": "Hello from the fixture",
            "truncated": False,
            "note": None,
        }
    ]
    binary = (await client.post(f"{base}/resources/read", json={"uri": "fixture://logo.png"})).json()
    assert binary[0]["text"] is None and binary[0]["note"].startswith("Binary content")
    missing = await client.post(f"{base}/resources/read", json={"uri": "fixture://nope"})
    assert missing.status_code == 409 and "No such resource" in missing.json()["error"]["message"]
    prompt = (
        await client.post(f"{base}/prompts/get", json={"name": "summarize", "arguments": {"topic": "tea"}})
    ).json()
    assert prompt == [{"role": "user", "text": "Summarize tea."}]
    await client.post(f"{base}/stop")
    stopped = await client.post(f"{base}/resources/read", json={"uri": "fixture://notes/hello"})
    assert stopped.status_code == 409 and "not running" in stopped.json()["error"]["message"]


async def test_problems_starting_are_kept_and_shown(
    client: httpx.AsyncClient, secret_store: MemorySecretStore
) -> None:
    r = await client.post("/api/mcp/servers", json=stdio_body(name="broken", command="no-such-program-xyz"))
    assert r.status_code == 201
    assert r.json()["status"] == "error" and "no-such-program-xyz" in r.json()["error"]
    # A missing secret (e.g. a wiped keychain) is named, not guessed at.
    server = await add(client)
    await client.post(f"/api/mcp/servers/{server['id']}/stop")
    await secret_store.delete(f"mcp:{server['id']}:env:fixture_token")
    again = (await client.post(f"/api/mcp/servers/{server['id']}/start")).json()
    assert again["status"] == "error" and "FIXTURE_TOKEN is missing" in again["error"]


async def test_enabled_servers_start_with_the_app(client: httpx.AsyncClient, app: FastAPI) -> None:
    server = await add(client)
    await add(client, name="off", enabled=False)
    c: AppContainer = app.state.container
    await c.mcp_manager.shutdown()  # as if NEXUS had just started
    assert c.tools.get("mcp__fixture__echo") is None
    await c.mcp.start_enabled(wait_s=10)
    assert c.tools.get("mcp__fixture__echo") is not None
    listed = {s["name"]: s["status"] for s in (await client.get("/api/mcp/servers")).json()}
    assert listed == {"fixture": "running", "off": "stopped"}
    assert server["id"]


# ---- streamable HTTP ----------------------------------------------------------------------------
@pytest.fixture
def http_server() -> Iterator[Any]:
    server = mcp_server.make_http_server(0, token=TOKEN_VALUE)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


async def test_http_servers_with_secret_headers(
    client: httpx.AsyncClient, app: FastAPI, http_server: Any
) -> None:
    url = f"http://127.0.0.1:{http_server.server_address[1]}/mcp"
    body = {
        "name": "remote",
        "transport": "http",
        "url": url,
        "secret_headers": {"Authorization": f"Bearer {TOKEN_VALUE}"},
    }
    r = await client.post("/api/mcp/servers", json=body)
    assert r.status_code == 201, r.text
    server = r.json()
    assert server["status"] == "running" and server["tools"] == 11
    assert server["secret_headers"] == ["Authorization"] and TOKEN_VALUE not in r.text
    rt = await make_rt(app, level=PermissionLevel.PERMISSIVE)
    assert (await rt.call("mcp__remote__add", {"a": 20, "b": 22})).text == "42"
    # A wrong token is reported plainly.
    r = await client.patch(
        f"/api/mcp/servers/{server['id']}", json={"secret_headers": {"Authorization": "Bearer wrong"}}
    )
    assert r.json()["status"] == "error" and "401" in r.json()["error"]
