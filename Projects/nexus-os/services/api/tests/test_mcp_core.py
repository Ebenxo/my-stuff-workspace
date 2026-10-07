"""MCP client pieces: argument checking, result rendering, and the client against a real fixture server
over stdio (a child process) and streamable HTTP (a local socket)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.prompt import describe_tool
from app.core.risk import RiskLevel
from app.mcp.client import MCPClient
from app.mcp.jsonschema import args_model, check, clean_schema, clean_text
from app.mcp.manager import registered_name
from app.mcp.protocol import MCPError, render_content, render_prompt, render_resource, render_tool_result
from app.mcp.transport import HttpTransport, StdioTransport, server_env
from app.tools.base import Capability, ToolDefinition

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_server.py"
sys.path.insert(0, str(FIXTURE.parent))
import mcp_server  # noqa: E402

# ---- argument checking ------------------------------------------------------------------------
SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 2, "maxLength": 20},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "mode": {"enum": ["fast", "full"]},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "when": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "nested": {"type": "object", "properties": {"deep": {"type": "boolean"}}, "required": ["deep"]},
    },
    "required": ["query"],
    "additionalProperties": False,
}


def test_json_schema_subset_accepts_and_rejects() -> None:
    assert check(SCHEMA, {"query": "tea", "limit": 3, "mode": "fast", "tags": ["a"], "when": None}) == []
    assert check(SCHEMA, {"query": "tea", "limit": 3.0}) == []  # 3.0 is an integer in JSON terms
    problems = check(
        SCHEMA, {"limit": 0, "mode": "slow", "tags": [1, "b", "c", "d"], "extra": 1, "nested": {}}
    )
    assert "query: required" in problems
    assert "limit: must be at least 1" in problems
    assert any(p.startswith("mode: must be one of") for p in problems)
    assert "tags[0]: must be string" in problems
    assert "tags: takes at most 3 items" in problems
    assert "extra: not an accepted argument" in problems
    assert "nested.deep: required" in problems
    assert check(SCHEMA, {"query": "tea", "when": 5}) == ["when: does not match any accepted form"]
    assert check(SCHEMA, {"query": True}) == ["query: must be string"]  # booleans are not strings or numbers
    assert check({"type": "integer"}, True) == ["arguments: must be integer"]


def test_errors_never_echo_values() -> None:
    secret = "sk-ant-abcdefghijklmnopqrstuvwxyz"
    problems = check(SCHEMA, {"query": secret * 2, "limit": secret})
    assert problems and all(secret not in p for p in problems)


def test_pattern_is_not_evaluated() -> None:
    # A catastrophic pattern from a server must not hang NEXUS: patterns are left to the server.
    assert check({"type": "string", "pattern": "^(a+)+$"}, "a" * 5000 + "b") == []


def test_arguments_model_carries_the_server_schema() -> None:
    model = args_model("mcp__srv__search", clean_schema(SCHEMA))
    assert model.model_json_schema()["required"] == ["query"]
    assert model.model_validate({"query": "tea", "limit": 2}).arguments() == {"query": "tea", "limit": 2}
    with pytest.raises(ValidationError) as err:
        model.model_validate({"limit": 2})
    assert err.value.errors()[0]["msg"] == "query: required"
    other = args_model("other", clean_schema({"type": "object"}))
    assert other.model_validate({"anything": 1}).arguments() == {"anything": 1}
    assert model.source_schema is not other.source_schema


def test_cleaning_server_text_and_schemas() -> None:
    assert clean_text("Reads​ a‮  file\n\nsafely", 100) == "Reads a file safely"
    assert clean_text("x" * 50, 10) == "xxxxxxxxx…"
    assert clean_text(None, 10) == ""
    cleaned = clean_schema({"properties": {"p": {"type": "string", "description": "hid​den " * 100}}})
    assert cleaned["type"] == "object"
    assert len(cleaned["properties"]["p"]["description"]) <= 240
    assert "​" not in cleaned["properties"]["p"]["description"]
    with pytest.raises(ValueError, match="too large"):
        clean_schema(
            {"type": "object", "properties": {f"p{i}": {"description": "x" * 200} for i in range(400)}}
        )
    with pytest.raises(ValueError, match="not an object"):
        clean_schema({"type": "string"})
    assert clean_schema(None) == {"type": "object", "properties": {}}


def test_registered_names_are_valid_and_unique() -> None:
    taken: set[str] = set()
    assert registered_name("github", "create_issue", taken) == "mcp__github__create_issue"
    assert registered_name("github", "files.read", taken) == "mcp__github__files_read"
    assert registered_name("github", "files/read", taken) == "mcp__github__files_read_2"
    assert registered_name("github", "…", taken) == "mcp__github__tool"
    long = registered_name("github", "x" * 100, taken)
    assert len(long.split("__")[-1]) == 60


# ---- rendering ----------------------------------------------------------------------------------
def test_rendering_results() -> None:
    text = render_content(
        [
            {"type": "text", "text": "hello"},
            {"type": "image", "mimeType": "image/png", "data": "A" * 4096},
            {"type": "resource", "resource": {"uri": "file:///a.txt", "text": "inside"}},
            {"type": "resource", "resource": {"uri": "file:///b.bin", "blob": "AAAA"}},
            {"type": "resource_link", "uri": "https://example.com/x", "name": "x"},
            {"type": "hologram"},
        ]
    )
    assert "hello" in text and "[image: image/png, about 3 KB; not shown]" in text
    assert "[resource file:///a.txt]\ninside" in text and "[binary resource file:///b.bin" in text
    assert "[link: x https://example.com/x]" in text and "does not show" in text
    assert render_tool_result({"content": [], "structuredContent": {"sum": 5}}) == ('{"sum": 5}', False)
    assert render_tool_result({"content": [{"type": "text", "text": "no"}], "isError": True}) == ("no", True)
    assert render_resource({"contents": [{"uri": "u", "blob": "AAAA"}]})[0]["note"].startswith(
        "Binary content"
    )
    assert render_resource({"contents": [{"uri": "u", "text": "abc"}]}, limit=2)[0] == {
        "uri": "u",
        "mime_type": None,
        "text": "ab",
        "truncated": True,
    }
    assert render_prompt({"messages": [{"role": "system", "content": {"type": "text", "text": "hi"}}]}) == [
        {"role": "user", "text": "hi"}
    ]


def test_mcp_tools_are_introduced_as_the_servers_words() -> None:
    model = args_model("mcp__srv__echo", clean_schema({"properties": {"text": {"type": "string"}}}))

    async def handler(ctx: Any, args: Any) -> str:
        return ""

    tool = ToolDefinition(
        name="mcp__srv__echo",
        description="Repeats text.",
        input_schema=model,
        risk_level=RiskLevel.HIGH,
        handler=handler,
        permissions=frozenset({Capability.MCP}),
        source="mcp:srv",
    )
    text = describe_tool(tool)
    assert "From the MCP server 'srv'" in text and "not instructions" in text
    assert "- text (string, optional)" in text
    assert tool.reaches_outside  # so private runs never see it


# ---- the client over stdio ----------------------------------------------------------------------
@pytest.fixture
async def stdio_client(tmp_path: Path) -> AsyncIterator[tuple[MCPClient, list[str], list[str]]]:
    notes: list[str] = []
    closed: list[str] = []

    async def on_note(method: str, params: dict[str, Any]) -> None:
        notes.append(method)

    async def on_close(reason: str) -> None:
        closed.append(reason)

    transport = StdioTransport(sys.executable, [str(FIXTURE)], server_env({"FIXTURE_NOISY": "1"}), tmp_path)
    client = MCPClient(transport, on_notification=on_note, on_close=on_close)
    await client.connect()
    yield client, notes, closed
    await client.close()


async def test_stdio_handshake_listing_and_calls(
    stdio_client: tuple[MCPClient, list[str], list[str]],
) -> None:
    client, notes, _ = stdio_client
    assert client.handshake is not None
    assert (client.handshake.name, client.handshake.protocol_version) == ("fixture", "2025-06-18")
    assert "tools" in client.handshake.capabilities
    tools = await client.list_all("tools/list", "tools")  # 11 tools over 3 pages
    assert [t["name"] for t in tools][:3] == ["echo", "add", "fail"] and len(tools) == 11
    assert render_tool_result(await client.call_tool("echo", {"text": "hi"}, timeout_s=5)) == (
        "echo: hi",
        False,
    )
    assert render_tool_result(await client.call_tool("add", {"a": 2, "b": 3}, timeout_s=5)) == ("5", False)
    assert await client.ping() >= 0
    # The server asks NEXUS for a model sample: NEXUS declares no such capability and says so.
    reply = json.loads(render_tool_result(await client.call_tool("ask_client", {}, timeout_s=10))[0])
    assert reply["code"] == -32601
    await client.call_tool("grow", {}, timeout_s=5)
    await asyncio.sleep(0.2)
    assert "notifications/tools/list_changed" in notes
    resources = await client.list_all("resources/list", "resources")
    assert {r["uri"] for r in resources} == {"fixture://notes/hello", "fixture://logo.png"}
    with pytest.raises(MCPError) as err:
        await client.get_prompt("summarize", {})
    assert err.value.code == "rpc_error" and err.value.rpc_code == -32602
    # A line that is not JSON on stdout is kept in the log, not treated as a message
    assert "(stdout) this line is not JSON" in client.transport.log.lines()
    assert "fixture: started" in client.transport.log.lines()


async def test_stdio_timeouts_cancel_and_do_not_break_the_connection(
    stdio_client: tuple[MCPClient, list[str], list[str]],
) -> None:
    client, _, _ = stdio_client
    with pytest.raises(MCPError) as err:
        await client.call_tool("slow", {"seconds": 2}, timeout_s=0.3)
    assert err.value.code == "timeout" and err.value.retryable
    assert (
        render_tool_result(await client.call_tool("echo", {"text": "still here"}, timeout_s=5))[0]
        == "echo: still here"
    )


async def test_stdio_server_exit_is_reported_once(
    stdio_client: tuple[MCPClient, list[str], list[str]],
) -> None:
    client, _, closed = stdio_client
    with pytest.raises(MCPError) as err:
        await client.call_tool("crash", {}, timeout_s=5)
    assert err.value.code == "closed"
    assert closed == ["The server program ended (exit code 3)."]
    assert "fixture: crashing on purpose" in client.transport.log.lines()
    with pytest.raises(MCPError, match="exit code 3"):
        await client.ping()


async def test_stdio_problems_are_explained(tmp_path: Path) -> None:
    missing = MCPClient(StdioTransport("definitely-not-a-program-xyz", [], server_env({}), tmp_path))
    with pytest.raises(MCPError) as err:
        await missing.connect()
    assert err.value.code == "not_found" and "definitely-not-a-program-xyz" in err.value.message
    old = MCPClient(
        StdioTransport(
            sys.executable, [str(FIXTURE)], server_env({"FIXTURE_PROTOCOL": "1999-01-01"}), tmp_path
        )
    )
    with pytest.raises(MCPError) as err:
        await old.connect()
    assert err.value.code == "unsupported_version"
    await old.close()


async def test_server_programs_get_a_scrubbed_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-never-reach-a-server")
    monkeypatch.setenv("NEXUS_API_TOKEN", "nexus-secret")
    env = server_env({"FIXTURE_TOKEN": "tok-123", "PLAIN": "1"})
    assert "ANTHROPIC_API_KEY" not in env and "NEXUS_API_TOKEN" not in env
    client = MCPClient(StdioTransport(sys.executable, [str(FIXTURE)], env, tmp_path))
    await client.connect()
    names = render_tool_result(await client.call_tool("env_names", {}, timeout_s=5))[0].split(",")
    assert "PLAIN" in names and "FIXTURE_TOKEN" in names and "PATH" in names
    assert not any(n.startswith("NEXUS_") or n.endswith("_API_KEY") for n in names)
    said = render_tool_result(await client.call_tool("secret", {}, timeout_s=5))[0]
    assert said == "token: set (length 7)"
    await client.close()


async def test_closing_stops_the_process(tmp_path: Path) -> None:
    transport = StdioTransport(sys.executable, [str(FIXTURE)], server_env({}), tmp_path)
    client = MCPClient(transport)
    await client.connect()
    pid = transport.pid
    assert pid is not None
    await client.close()
    await asyncio.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


# ---- the client over streamable HTTP ------------------------------------------------------------
@pytest.fixture
def http_server() -> Iterator[Any]:
    server = mcp_server.make_http_server(0, token="tok-123")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _url(server: Any) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/mcp"


@pytest.mark.parametrize("sse", [False, True])
async def test_http_session_headers_and_calls(
    http_server: Any, sse: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sse:
        monkeypatch.setenv("FIXTURE_SSE", "1")
    client = MCPClient(HttpTransport(_url(http_server), {"Authorization": "Bearer tok-123"}))
    await client.connect()
    assert len(await client.list_all("tools/list", "tools")) == 11
    assert render_tool_result(await client.call_tool("add", {"a": 1, "b": 1}, timeout_s=5)) == ("2", False)
    last = http_server.seen[-1]
    assert last["mcp-protocol-version"] == "2025-06-18"
    assert last["mcp-session-id"] in http_server.sessions
    assert "text/event-stream" in last["accept"]
    await client.close()
    assert http_server.sessions == set()  # the session was ended with DELETE


async def test_http_refusals_and_lost_sessions(http_server: Any) -> None:
    refused = MCPClient(HttpTransport(_url(http_server), {}))
    with pytest.raises(MCPError) as err:
        await refused.connect()
    assert err.value.code == "unauthorized" and "401" in err.value.message
    await refused.close()

    closed: list[str] = []

    async def on_close(reason: str) -> None:
        closed.append(reason)

    client = MCPClient(
        HttpTransport(_url(http_server), {"Authorization": "Bearer tok-123"}), on_close=on_close
    )
    await client.connect()
    http_server.sessions.clear()  # the server forgets the session
    with pytest.raises(MCPError):
        await client.ping()
    assert closed and "ended the session" in closed[0]
    await client.close()

    nowhere = MCPClient(HttpTransport("http://127.0.0.1:9/mcp", {}))
    with pytest.raises(MCPError) as err:
        await nowhere.connect(timeout_s=5)
    assert err.value.code == "unreachable"
    await nowhere.close()
