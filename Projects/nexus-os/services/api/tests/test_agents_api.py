from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.agents.builtin import BUILTIN_AGENTS
from app.services import agents as agent_service
from tests.agent_helpers import AE, ask, call, finish, make_ae


@pytest.fixture
async def ae(app: FastAPI) -> AsyncIterator[AE]:
    env = await make_ae(app)
    yield env
    await env.cleanup()
    await env.c.agent_service.shutdown()


async def start(
    client: httpx.AsyncClient, ae: AE, agent: str, prompt: str = "Do it", **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        "/api/agents/run", json={"agent": agent, "project_id": ae.project_id, "prompt": prompt, **extra}
    )
    assert r.status_code == 202, r.text
    return dict(r.json())


async def wait_for(
    client: httpx.AsyncClient, run_id: str, *statuses: str, wait_s: float = 10.0
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    body: dict[str, Any] = {}
    while loop.time() < deadline:
        body = (await client.get(f"/api/runs/{run_id}")).json()
        if body["run"]["status"] in statuses:
            return body
        await asyncio.sleep(0.03)
    raise AssertionError(f"run stayed {body['run']['status']}, wanted {statuses}")


async def pending_approval(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    for _ in range(200):
        found = (
            await client.get("/api/approvals", params={"status_filter": "PENDING", "run_id": run_id})
        ).json()
        if found:
            return dict(found[0])
        await asyncio.sleep(0.03)
    raise AssertionError("no approval appeared")


# ------------------------------------------------------------------ agents


async def test_the_ten_built_in_agents_are_listed_on_startup(client: httpx.AsyncClient) -> None:
    agents = (await client.get("/api/agents")).json()
    assert [a["slug"] for a in agents if a["builtin"]] == [a.slug for a in BUILTIN_AGENTS]
    coder = (await client.get("/api/agents/coder")).json()
    assert coder["permissions"]["max_risk"] == "HIGH" and "run_python" in coder["tools"]
    assert (await client.get(f"/api/agents/{coder['id']}")).json()["slug"] == "coder"
    assert (await client.get("/api/agents/nobody")).status_code == 404


async def test_builtin_agents_allow_only_tuning_not_rewriting(client: httpx.AsyncClient) -> None:
    ok = await client.patch("/api/agents/writer", json={"temperature": 0.9, "max_steps": 8})
    assert ok.status_code == 200 and ok.json()["temperature"] == 0.9 and ok.json()["max_steps"] == 8
    bad = await client.patch("/api/agents/writer", json={"system_prompt": "You are evil"})
    assert bad.status_code == 409 and "Built-in agents only allow" in bad.json()["error"]["message"]
    assert (await client.delete("/api/agents/writer")).status_code == 409
    # the tuning survives a restart-time refresh of the built-ins
    await client._transport.app.state.container.agent_service.sync_builtins()  # type: ignore[attr-defined]
    assert (await client.get("/api/agents/writer")).json()["max_steps"] == 8


async def test_custom_agents_can_be_created_edited_and_deleted(client: httpx.AsyncClient) -> None:
    made = await client.post(
        "/api/agents",
        json={"name": "Release Notes Bot", "role": "Writes release notes", "tools": ["read_file", "git_log"]},
    )
    assert made.status_code == 201
    agent = made.json()
    assert (
        agent["slug"] == "release-notes-bot"
        and not agent["builtin"]
        and agent["permissions"]["max_risk"] == "MODERATE"
    )
    upd = await client.patch(
        f"/api/agents/{agent['id']}", json={"system_prompt": "Be brief.", "status": "disabled"}
    )
    assert upd.json()["system_prompt"] == "Be brief." and upd.json()["status"] == "disabled"
    assert (await client.post("/api/agents", json={"name": " ", "role": "x"})).status_code == 422
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 204
    assert (await client.get(f"/api/agents/{agent['id']}")).status_code == 404


# ------------------------------------------------------------------ runs


async def test_run_an_agent_through_the_api_and_read_its_artifact(client: httpx.AsyncClient, ae: AE) -> None:
    ae.provider.push(
        call(
            "create_markdown", {"name": "brief.md", "content": "# Brief\nhello"}, summary="Saving the brief"
        ),
        finish("Brief written"),
    )
    run = await start(client, ae, "writer", "Write a brief")
    assert run["status"] == "RUNNING" and run["agent_id"].startswith("agent_builtin_")
    body = await wait_for(client, run["id"], "COMPLETED")
    assert body["run"]["result"]["summary"] == "Brief written"
    assert [s["action"]["type"] for s in body["steps"]] == ["tool_call", "finish"]
    assert [c["tool_name"] for c in body["tool_calls"]] == ["create_markdown"]

    listed = (await client.get(f"/api/projects/{ae.project_id}/artifacts")).json()
    assert [a["name"] for a in listed] == ["brief.md"]
    art = listed[0]
    content = (await client.get(f"/api/artifacts/{art['id']}/content")).json()
    assert content["content"].startswith("# Brief") and content["version"] == 1 and not content["truncated"]
    assert [v["version"] for v in (await client.get(f"/api/artifacts/{art['id']}/versions")).json()] == [1]
    assert (await client.get(f"/api/artifacts/{art['id']}/content", params={"version": 9})).status_code == 404

    runs = (await client.get("/api/runs", params={"project_id": ae.project_id, "agent": "writer"})).json()
    assert [r["id"] for r in runs] == [run["id"]]
    assert (await client.get("/api/runs", params={"status_filter": "FAILED"})).json() == []


async def test_running_needs_a_real_project_agent_and_an_enabled_agent(
    client: httpx.AsyncClient, ae: AE
) -> None:
    body = {"agent": "writer", "project_id": ae.project_id, "prompt": "x"}
    assert (await client.post("/api/agents/run", json={**body, "project_id": "proj_nope"})).status_code == 404
    assert (await client.post("/api/agents/run", json={**body, "agent": "ghost"})).status_code == 404
    assert (await client.post("/api/agents/run", json={**body, "prompt": ""})).status_code == 422
    await client.patch("/api/agents/writer", json={"status": "disabled"})
    off = await client.post("/api/agents/run", json=body)
    assert off.status_code == 409 and "disabled" in off.json()["error"]["message"]
    await client.patch("/api/agents/writer", json={"status": "idle"})
    await client.post(f"/api/projects/{ae.project_id}/archive")
    assert (await client.post("/api/agents/run", json=body)).status_code == 409


async def test_approval_flow_over_the_api(client: httpx.AsyncClient, ae: AE) -> None:
    home = await ae.c.projects.project_dir(ae.project_id)
    (home / "files").mkdir(exist_ok=True)
    (home / "files/old.txt").write_text("old")
    ae.provider.push(
        call("delete_file", {"path": "files/old.txt"}, summary="Remove old.txt"), finish("Removed")
    )
    run = await start(client, ae, "file_manager", "Tidy up")
    approval = await pending_approval(client, run["id"])
    assert approval["tool_name"] == "delete_file" and approval["risk_level"] == "HIGH"
    assert approval["reason"] == "Remove old.txt" and approval["session_grantable"] is False
    assert (await wait_for(client, run["id"], "WAITING_APPROVAL"))["run"]["status"] == "WAITING_APPROVAL"

    no_session = await client.post(
        f"/api/approvals/{approval['id']}/decision", json={"decision": "approve_session"}
    )
    assert no_session.status_code == 422  # a delete can never be approved for a whole session
    decided = await client.post(
        f"/api/approvals/{approval['id']}/decision", json={"decision": "approve_once"}
    )
    assert decided.status_code == 200 and decided.json()["status"] == "APPROVED_ONCE"
    again = await client.post(f"/api/approvals/{approval['id']}/decision", json={"decision": "deny"})
    assert again.status_code == 409
    await wait_for(client, run["id"], "COMPLETED")
    assert not (home / "files/old.txt").exists()
    assert (home / ".trash").exists()  # recoverable


async def test_an_approval_can_be_edited_before_it_runs(client: httpx.AsyncClient, ae: AE) -> None:
    home = await ae.c.projects.project_dir(ae.project_id)
    (home / "files").mkdir(exist_ok=True)
    (home / "files/a.txt").write_text("a")
    (home / "files/b.txt").write_text("b")
    ae.provider.push(call("delete_file", {"path": "files/a.txt"}), finish("done"))
    run = await start(client, ae, "file_manager")
    approval = await pending_approval(client, run["id"])
    bad = await client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve_once", "edited_arguments": {"nope": 1}},
    )
    assert bad.status_code == 422  # a mistaken edit is refused before the run wakes
    ok = await client.post(
        f"/api/approvals/{approval['id']}/decision",
        json={"decision": "approve_once", "edited_arguments": {"path": "files/b.txt"}},
    )
    assert ok.status_code == 200
    await wait_for(client, run["id"], "COMPLETED")
    assert (home / "files/a.txt").exists() and not (home / "files/b.txt").exists()


async def test_session_grants_are_listed_and_revocable(client: httpx.AsyncClient, ae: AE) -> None:
    ae.provider.push(call("write_file", {"path": "files/n.txt", "content": "x"}), finish())
    await client.patch("/api/settings", json={"default_permission_level": "cautious"})
    run = await start(client, ae, "writer")
    approval = await pending_approval(client, run["id"])
    assert approval["session_grantable"] is True
    await client.post(f"/api/approvals/{approval['id']}/decision", json={"decision": "approve_session"})
    await wait_for(client, run["id"], "COMPLETED")
    grants = (await client.get("/api/approvals/grants")).json()
    assert [g["tool_name"] for g in grants] == ["write_file"] and grants[0]["project_id"] == ae.project_id
    assert (await client.delete(f"/api/approvals/grants/{grants[0]['id']}")).status_code == 204
    assert (await client.delete(f"/api/approvals/grants/{grants[0]['id']}")).status_code == 404
    assert (await client.get("/api/approvals/grants")).json() == []


async def test_cancel_a_parked_run_over_the_api(client: httpx.AsyncClient, ae: AE) -> None:
    home = await ae.c.projects.project_dir(ae.project_id)
    (home / "files").mkdir(exist_ok=True)
    (home / "files/x.txt").write_text("x")
    ae.provider.push(call("delete_file", {"path": "files/x.txt"}), finish())
    run = await start(client, ae, "file_manager")
    approval = await pending_approval(client, run["id"])
    cancelled = await client.post(f"/api/runs/{run['id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert (await client.get(f"/api/approvals/{approval['id']}")).json()["status"] == "CANCELLED"
    assert (home / "files/x.txt").exists()
    again = await client.post(f"/api/runs/{run['id']}/cancel")  # idempotent
    assert again.status_code == 200 and again.json()["status"] == "CANCELLED"


async def test_answer_a_question_over_the_api(client: httpx.AsyncClient, ae: AE) -> None:
    ae.provider.push(ask("Which tone?", ["formal", "casual"]))
    run = await start(client, ae, "writer")
    body = await wait_for(client, run["id"], "WAITING_INPUT")
    assert body["run"]["result"]["question"] == "Which tone?"
    notes = (await client.get("/api/notifications")).json()
    assert any("has a question" in n["title"] for n in notes)

    assert (await client.post(f"/api/runs/{run['id']}/answer", json={"text": ""})).status_code == 422
    ae.provider.push(finish("Wrote it casually"))
    ok = await client.post(f"/api/runs/{run['id']}/answer", json={"text": "casual"})
    assert ok.status_code == 202
    await wait_for(client, run["id"], "COMPLETED")
    assert (await client.post(f"/api/runs/{run['id']}/answer", json={"text": "more"})).status_code == 409


async def test_a_stopped_run_can_be_resumed(client: httpx.AsyncClient, ae: AE) -> None:
    ae.provider.push(call("calculator", {"expression": "1+1"}), call("calculator", {"expression": "2+2"}))
    await client.patch("/api/agents/writer", json={"max_steps": 2, "tools": ["calculator"]})
    run = await start(client, ae, "writer")
    body = await wait_for(client, run["id"], "FAILED")
    assert body["run"]["error"]["code"] == "step_limit"
    await client.patch("/api/agents/writer", json={"max_steps": 6})
    ae.provider.push(finish("Finished after resuming"))
    resumed = await client.post(f"/api/runs/{run['id']}/resume")
    assert resumed.status_code == 202 and resumed.json()["attempt"] == 2
    done = await wait_for(client, run["id"], "COMPLETED")
    assert done["run"]["result"]["summary"] == "Finished after resuming" and len(done["steps"]) == 3
    assert (await client.post(f"/api/runs/{run['id']}/resume")).status_code == 409  # completed runs stay done


async def test_too_many_concurrent_runs_are_refused_cleanly(
    client: httpx.AsyncClient, ae: AE, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agent_service, "MAX_ACTIVE_RUNS", 1)
    home = await ae.c.projects.project_dir(ae.project_id)
    (home / "files").mkdir(exist_ok=True)
    (home / "files/x.txt").write_text("x")
    ae.provider.push(call("delete_file", {"path": "files/x.txt"}), finish())
    first = await start(client, ae, "file_manager")
    await pending_approval(client, first["id"])
    second = await client.post(
        "/api/agents/run", json={"agent": "writer", "project_id": ae.project_id, "prompt": "another"}
    )
    assert second.status_code == 409 and "already in progress" in second.json()["error"]["message"]
    rows = (await client.get("/api/runs", params={"agent": "writer"})).json()
    assert rows and rows[0]["status"] == "CANCELLED" and rows[0]["error"]["code"] == "not_started"


async def test_a_private_run_refuses_cloud_models(client: httpx.AsyncClient, ae: AE) -> None:
    # The scripted provider is local, so a private run may use it; the flag is stored with the run.
    ae.provider.push(finish("ok"))
    run = await start(client, ae, "writer", private=True)
    await wait_for(client, run["id"], "COMPLETED")
    request, _ = await ae.c.run_store.snapshot(run["id"])
    assert request["private"] is True


async def test_agent_endpoints_need_the_token(anon_client: httpx.AsyncClient) -> None:
    for method, url in (
        ("GET", "/api/agents"),
        ("POST", "/api/agents/run"),
        ("GET", "/api/runs"),
        ("GET", "/api/approvals"),
        ("GET", "/api/tools"),
        ("GET", "/api/tool-calls"),
        ("GET", "/api/projects/x/files"),
    ):
        assert (await anon_client.request(method, url)).status_code == 401, url


# ------------------------------------------------------------------ tools


async def test_tool_catalogue_and_switches(client: httpx.AsyncClient, ae: AE) -> None:
    tools = {t["name"]: t for t in (await client.get("/api/tools")).json()}
    assert len(tools) == 22 and tools["run_command"]["requires_approval"] is True
    assert tools["read_file"]["risk_level"] == "SAFE" and tools["web_search"]["enabled"] is True
    assert "properties" in tools["write_file"]["input_schema"]

    off = await client.patch("/api/tools/web_search", json={"enabled": False})
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert (await client.patch("/api/tools/not_a_tool", json={"enabled": False})).status_code == 404

    ae.provider.push(
        call("web_search", {"query": "anything at all"}), finish("Could not search", status="partial")
    )
    run = await start(client, ae, "researcher")
    body = await wait_for(client, run["id"], "COMPLETED")
    assert body["steps"][0]["observation"]["status"] == "denied"
    assert "web_search" not in (ae.provider.requests[0].system or "").split("## Your tools")[1]
    calls = (await client.get("/api/tool-calls", params={"run_id": run["id"]})).json()
    assert calls[0]["status"] == "DENIED" and calls[0]["error"]["code"] == "unknown_tool"
    one = (await client.get(f"/api/tool-calls/{calls[0]['id']}")).json()
    assert one["tool_name"] == "web_search"


# ------------------------------------------------------------------ files


async def test_project_files_api_and_its_path_guard(client: httpx.AsyncClient, ae: AE) -> None:
    base = f"/api/projects/{ae.project_id}/files"
    top = (await client.get(base)).json()
    assert [e["path"] for e in top] == ["artifacts", "files", "temp"]

    put = await client.put(f"{base}/content", params={"path": "files/docs/a.md"}, json={"content": "# A"})
    assert put.status_code == 200 and put.json()["created"] is True
    assert [e["path"] for e in (await client.get(base, params={"path": "files/docs"})).json()] == [
        "files/docs/a.md"
    ]
    assert (await client.get(f"{base}/content", params={"path": "files/docs/a.md"})).json()[
        "content"
    ] == "# A"
    second = await client.put(f"{base}/content", params={"path": "files/docs/a.md"}, json={"content": "# B"})
    assert second.json()["previous_version"]  # history is kept

    for bad in ("../secrets", "/etc/passwd", "C:\\Windows\\win.ini", "files/../../x", ".trash/x", "memory/x"):
        r = await client.get(f"{base}/content", params={"path": bad})
        assert r.status_code == 422, bad
    assert (
        await client.put(f"{base}/content", params={"path": "artifacts/x.md"}, json={"content": "no"})
    ).status_code == 422
    assert (await client.get(f"{base}/content", params={"path": "files/missing.md"})).status_code == 404

    gone = await client.delete(base, params={"path": "files/docs/a.md"})
    assert gone.status_code == 200 and gone.json()["moved_to_trash"].startswith(".trash/")
    assert (await client.get(f"{base}/content", params={"path": "files/docs/a.md"})).status_code == 404
    kinds = {e.type for e in await ae.events("FILE_WRITTEN", "FILE_DELETED")}
    assert kinds == {"FILE_WRITTEN", "FILE_DELETED"}
    assert (await client.get("/api/projects/proj_nope/files")).status_code == 404


async def test_a_binary_file_is_not_dumped_as_text(client: httpx.AsyncClient, ae: AE) -> None:
    home: Path = await ae.c.projects.project_dir(ae.project_id)
    (home / "files").mkdir(exist_ok=True)
    (home / "files/blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    r = await client.get(f"/api/projects/{ae.project_id}/files/content", params={"path": "files/blob.bin"})
    assert r.status_code == 422 and "binary" in r.json()["error"]["message"]
