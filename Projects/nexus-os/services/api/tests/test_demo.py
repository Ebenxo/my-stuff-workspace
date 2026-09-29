from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.services.demo import DEMO_OBJECTIVE, REPORT


async def settle(client: httpx.AsyncClient, oid: str, *statuses: str, wait_s: float = 20) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    body: dict[str, Any] = {}
    while loop.time() < deadline:
        body = (await client.get(f"/api/objectives/{oid}")).json()
        if body["objective"]["status"] in statuses:
            return body
        await asyncio.sleep(0.03)
    raise AssertionError(
        f"demo stayed {body.get('objective', {}).get('status')}: {body.get('objective', {}).get('error')}"
    )


async def test_the_demo_runs_end_to_end_offline_with_real_orchestration(client: httpx.AsyncClient) -> None:
    started = await client.post("/api/demo")
    assert started.status_code == 202, started.text
    obj = started.json()
    assert obj["text"] == DEMO_OBJECTIVE and obj["model"].endswith(":demo:scripted")

    body = await settle(client, obj["id"], "AWAITING_PLAN_APPROVAL")
    plan = body["objective"]["plan"]
    assert [t["agent"] for t in plan["tasks"]] == ["researcher", "writer"]
    assert plan["tasks"][1]["review"] is True and len(plan["completion_criteria"]) == 4

    project = (await client.get(f"/api/projects/{obj['project_id']}")).json()
    assert project["is_demo"] is True
    note = (
        await client.get(
            f"/api/projects/{project['id']}/files/content", params={"path": "files/notes/gamma-dev.md"}
        )
    ).json()
    assert note["content"].startswith("> DEMO DATA")  # the demo labels its own data

    assert (await client.post(f"/api/objectives/{obj['id']}/run", json={})).status_code == 202
    body = await settle(client, obj["id"], "COMPLETED")
    keys = [t["key"] for t in body["tasks"]]
    assert keys == ["t1", "t2", "t2-review1", "t2-rev1", "t2-review2", "verify1"]
    result = body["objective"]["result"]
    assert result["verdict"] == "PASS" and all(c["met"] for c in result["criteria"])
    assert [(a["name"], a["version"]) for a in result["artifacts"]] == [(REPORT, 2)]

    arts = (await client.get(f"/api/projects/{project['id']}/artifacts")).json()
    content = (await client.get(f"/api/artifacts/{arts[0]['id']}/content")).json()["content"]
    assert "| Gamma Dev | $15 per user per month |" in content  # the Critic's issue was fixed
    first = (await client.get(f"/api/artifacts/{arts[0]['id']}/content", params={"version": 1})).json()[
        "content"
    ]
    assert "| Gamma Dev | — |" in first  # and the first draft is still kept

    kinds = {m["type"] for m in body["messages"]}
    assert {"TASK_REQUEST", "TASK_RESULT", "REVIEW_REQUEST", "REVIEW_RESULT"} <= kinds
    events = (await client.get("/api/events", params={"limit": 500})).json()
    types = {e["type"] for e in events if e.get("objective_id") == obj["id"]}
    for t in (
        "PLAN_CREATED",
        "PLAN_APPROVED",
        "TASK_STARTED",
        "TOOL_CALLED",
        "REVIEW_COMPLETED",
        "VERIFICATION_COMPLETED",
        "ARTIFACT_UPDATED",
        "OBJECTIVE_COMPLETED",
    ):
        assert t in types, t


async def test_the_demo_model_never_answers_real_work(client: httpx.AsyncClient) -> None:
    started = (await client.post("/api/demo")).json()
    await settle(client, started["id"], "AWAITING_PLAN_APPROVAL")
    # Only the demo provider exists; a real objective must not be routed to its script.
    other = (await client.post("/api/projects", json={"name": "Real work"})).json()
    real = (
        await client.post("/api/objectives", json={"project_id": other["id"], "text": "Plan my week"})
    ).json()
    body = await settle(client, real["id"], "FAILED")
    assert "demo provider only runs the demo project" in body["objective"]["error"]["message"]


async def test_only_one_demo_runs_at_a_time_and_it_can_run_again(client: httpx.AsyncClient) -> None:
    first = (await client.post("/api/demo")).json()
    await settle(client, first["id"], "AWAITING_PLAN_APPROVAL")
    again = await client.post("/api/demo")
    assert again.status_code == 409 and "already running" in again.json()["error"]["message"]
    await client.post(f"/api/objectives/{first['id']}/cancel")
    second = await client.post("/api/demo")
    assert (
        second.status_code == 202 and second.json()["project_id"] == first["project_id"]
    )  # the demo project is reused
    await settle(client, second.json()["id"], "AWAITING_PLAN_APPROVAL")
    await client.post(f"/api/objectives/{second.json()['id']}/run", json={})
    assert (await settle(client, second.json()["id"], "COMPLETED"))["objective"]["result"][
        "verdict"
    ] == "PASS"
