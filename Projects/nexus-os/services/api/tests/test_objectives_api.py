from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from tests.objective_helpers import OE, call, finish, make_oe, plan, verdict


@pytest.fixture
async def oe(app: FastAPI) -> AsyncIterator[OE]:
    env = await make_oe(app)
    yield env
    await env.c.objective_service.shutdown()
    env.c.orchestrator.shutting_down = env.c.runner.shutting_down = False


async def settle(client: httpx.AsyncClient, oid: str, *statuses: str, wait_s: float = 15) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    body: dict[str, Any] = {}
    while loop.time() < deadline:
        body = (await client.get(f"/api/objectives/{oid}")).json()
        if body["objective"]["status"] in statuses:
            return body
        await asyncio.sleep(0.03)
    raise AssertionError(f"objective stayed {body.get('objective', {}).get('status')}, wanted {statuses}")


async def test_objective_lifecycle_over_the_api(client: httpx.AsyncClient, oe: OE) -> None:
    oe.book.add(
        "Planner", plan([{"key": "t1", "title": "Write the brief", "agent": "writer", "review": True}])
    )
    r = await client.post(
        "/api/objectives",
        json={"project_id": oe.project_id, "text": "Write a one-page brief", "run_mode": "review_plan"},
    )
    assert r.status_code == 202 and r.json()["status"] == "RECEIVED"
    oid = r.json()["id"]

    body = await settle(client, oid, "AWAITING_PLAN_APPROVAL")
    assert body["objective"]["plan"]["tasks"][0]["key"] == "t1"
    assert body["objective"]["strategy"]["name"] == "reviewer"
    assert [t["status"] for t in body["tasks"]] == ["WAITING"]
    assert any(m["sender"] == "planner" for m in body["messages"])

    listed = (await client.get("/api/objectives", params={"project_id": oe.project_id})).json()
    assert [o["id"] for o in listed] == [oid]
    assert (await client.get("/api/objectives", params={"status_filter": "COMPLETED"})).json() == []

    edited = await client.put(
        f"/api/objectives/{oid}/plan",
        json={
            "tasks": [{"key": "t1", "title": "Write the brief", "description": "One page", "agent": "writer"}]
        },
    )
    assert edited.status_code == 200 and edited.json()["tasks"][0]["review"] is False
    bad = await client.put(
        f"/api/objectives/{oid}/plan",
        json={"tasks": [{"key": "t1", "title": "x", "description": "", "agent": "wizard"}]},
    )
    assert bad.status_code == 422 and "unknown agent" in bad.json()["error"]["message"]

    oe.book.add(
        "Writer",
        call("create_markdown", {"name": "brief.md", "content": "# Brief"}),
        finish("Saved the brief"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    run = await client.post(f"/api/objectives/{oid}/run", json={"mode": "normal"})
    assert run.status_code == 202
    body = await settle(client, oid, "COMPLETED")
    result = body["objective"]["result"]
    assert result["verdict"] == "PASS" and [a["name"] for a in result["artifacts"]] == ["brief.md"]
    task = body["tasks"][0]
    one = (await client.get(f"/api/tasks/{task['id']}")).json()
    assert one["status"] == "COMPLETED" and one["outputs"]["summary"] == "Saved the brief" and one["run_id"]
    assert (await client.post(f"/api/objectives/{oid}/run", json={})).status_code == 409
    assert (await client.post(f"/api/objectives/{oid}/resume")).status_code == 409


async def test_blocked_tasks_can_be_answered_retried_and_skipped_over_the_api(
    client: httpx.AsyncClient, oe: OE
) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add(
        "Writer",
        {"summary": "?", "action": {"type": "ask_human", "question": "Which audience?", "options": []}},
        finish("Done"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    oid = (
        await client.post(
            "/api/objectives", json={"project_id": oe.project_id, "text": "Write it", "run_mode": "auto"}
        )
    ).json()["id"]
    body = await settle(client, oid, "PAUSED")
    t1 = body["tasks"][0]
    assert t1["status"] == "BLOCKED" and t1["error"]["message"] == "Which audience?"
    assert (await client.post(f"/api/tasks/{t1['id']}/answer", json={"text": ""})).status_code == 422
    assert (await client.post(f"/api/tasks/{t1['id']}/answer", json={"text": "Engineers"})).status_code == 202
    await settle(client, oid, "COMPLETED")
    for action in ("retry", "skip"):
        assert (await client.post(f"/api/tasks/{t1['id']}/{action}")).status_code == 409
    assert (await client.post(f"/api/tasks/{t1['id']}/answer", json={"text": "again"})).status_code == 409


async def test_cancel_over_the_api(client: httpx.AsyncClient, oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oid = (
        await client.post(
            "/api/objectives",
            json={"project_id": oe.project_id, "text": "Write it", "run_mode": "review_plan"},
        )
    ).json()["id"]
    await settle(client, oid, "AWAITING_PLAN_APPROVAL")
    r = await client.post(f"/api/objectives/{oid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    body = (await client.get(f"/api/objectives/{oid}")).json()
    assert [t["status"] for t in body["tasks"]] == ["CANCELLED"]


async def test_objective_requests_are_validated(client: httpx.AsyncClient, oe: OE) -> None:
    assert (
        await client.post("/api/objectives", json={"project_id": oe.project_id, "text": "  "})
    ).status_code == 422
    assert (
        await client.post("/api/objectives", json={"project_id": "proj_nope", "text": "Write it"})
    ).status_code == 404
    assert (
        await client.post(
            "/api/objectives", json={"project_id": oe.project_id, "text": "Write it", "run_mode": "yolo"}
        )
    ).status_code == 422
    assert (await client.get("/api/objectives/obj_nope")).status_code == 404
    assert (await client.get("/api/tasks/task_nope")).status_code == 404


async def test_objective_endpoints_need_the_token(anon_client: httpx.AsyncClient) -> None:
    for method, url in (("GET", "/api/objectives"), ("POST", "/api/objectives"), ("GET", "/api/tasks/x")):
        assert (await anon_client.request(method, url)).status_code == 401
