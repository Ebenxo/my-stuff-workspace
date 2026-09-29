"""Workflows, runs and schedules over HTTP, and the scheduler's ticking rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.services.container import AppContainer


@pytest.fixture
async def project_id(client: httpx.AsyncClient) -> str:
    return str((await client.post("/api/projects", json={"name": "Flows"})).json()["id"])


def flow(
    values: dict[str, str], inputs: list[dict[str, Any]] | None = None, gate: bool = False
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": "start", "type": "trigger"}]
    edges: list[dict[str, Any]] = []
    last = "start"
    if gate:
        nodes.append({"id": "gate", "type": "approval", "config": {"message": "Go?"}})
        edges.append({"id": "e0", "source": "start", "target": "gate"})
        last = "gate"
    nodes.append({"id": "out", "type": "output", "config": {"values": values}})
    edges.append({"id": "e1", "source": last, "target": "out"})
    return {"inputs": inputs or [], "nodes": nodes, "edges": edges}


async def settle(app: FastAPI, run_id: str) -> dict[str, Any]:
    c: AppContainer = app.state.container
    return (await c.workflows.wait_for(run_id)).model_dump(mode="json")


async def test_workflow_lifecycle_over_http(app: FastAPI, client: httpx.AsyncClient, project_id: str) -> None:
    r = await client.post("/api/workflows", json={"name": "Starter", "project_id": project_id})
    assert r.status_code == 201
    starter = r.json()
    assert starter["version"] == 1 and [n["type"] for n in starter["definition"]["nodes"]] == [
        "trigger",
        "agent",
        "output",
    ]

    body = {
        "name": "Greeter",
        "project_id": project_id,
        "definition": flow({"greeting": "'Hello ' + inputs.name"}, [{"name": "name"}]),
    }
    wf = (await client.post("/api/workflows", json=body)).json()
    assert [
        w["name"] for w in (await client.get("/api/workflows", params={"project_id": project_id})).json()
    ] == ["Greeter", "Starter"]

    run = await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {"name": "Ada"}})
    assert run.status_code == 202
    done = await settle(app, run.json()["id"])
    assert done["status"] == "COMPLETED" and done["outputs"] == {"greeting": "Hello Ada"}
    detail = (await client.get(f"/api/workflow-runs/{done['id']}")).json()
    assert detail["name"] == "Greeter" and detail["definition"]["nodes"][1]["id"] == "out"
    assert [x["id"] for x in (await client.get(f"/api/workflows/{wf['id']}/runs")).json()] == [done["id"]]
    assert [
        x["id"] for x in (await client.get("/api/workflow-runs", params={"project_id": project_id})).json()
    ] == [done["id"]]

    renamed = (
        await client.put(
            f"/api/workflows/{wf['id']}",
            json={
                "name": "Greeter 2",
                "definition": flow({"greeting": "'Hi ' + inputs.name"}, [{"name": "name"}]),
            },
        )
    ).json()
    assert renamed["version"] == 2 and renamed["name"] == "Greeter 2"
    assert [v["version"] for v in (await client.get(f"/api/workflows/{wf['id']}/versions")).json()] == [2, 1]

    bad = await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    assert bad.status_code == 422 and "'name' is required" in bad.text
    assert (await client.delete(f"/api/workflows/{wf['id']}")).status_code == 204
    assert (await client.get(f"/api/workflows/{wf['id']}")).status_code == 404
    # its run history is kept
    assert (await client.get(f"/api/workflow-runs/{done['id']}")).json()["name"] == "Greeter 2"


async def test_validate_endpoint(client: httpx.AsyncClient, project_id: str) -> None:
    good = await client.post(
        "/api/workflows/validate", json={"project_id": project_id, "definition": flow({"x": "1"})}
    )
    assert good.json() == {"ok": True, "issues": []}
    broken = flow({"x": "inputs.("})
    broken["nodes"].append({"id": "a", "type": "agent", "config": {"agent": "ghost", "prompt": "hi"}})
    report = (
        await client.post("/api/workflows/validate", json={"project_id": project_id, "definition": broken})
    ).json()
    assert not report["ok"]
    messages = [i["message"] for i in report["issues"]]
    assert (
        any("ghost" in m for m in messages)
        and any("not connected" in m for m in messages)
        and any("inputs.(" in m for m in messages)
    )
    # a workflow with issues can be saved (work in progress) but not run
    wf = (
        await client.post(
            "/api/workflows", json={"name": "WIP", "project_id": project_id, "definition": broken}
        )
    ).json()
    r = await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})
    assert r.status_code == 422 and "cannot run yet" in r.text


async def test_approval_steps_over_http(app: FastAPI, client: httpx.AsyncClient, project_id: str) -> None:
    wf = (
        await client.post(
            "/api/workflows",
            json={"name": "Gated", "project_id": project_id, "definition": flow({"ok": "true"}, gate=True)},
        )
    ).json()
    run = (await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})).json()
    waiting = await settle(app, run["id"])
    assert waiting["status"] == "WAITING" and waiting["node_states"]["gate"]["output"] == {"message": "Go?"}
    assert (
        await client.post(f"/api/workflow-runs/{run['id']}/nodes/out/approve", json={})
    ).status_code == 409
    assert (
        await client.post(f"/api/workflow-runs/{run['id']}/nodes/nope/approve", json={})
    ).status_code == 422
    r = await client.post(f"/api/workflow-runs/{run['id']}/nodes/gate/approve", json={"note": "fine"})
    assert r.status_code == 200
    assert (await settle(app, run["id"]))["status"] == "COMPLETED"
    run2 = (await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})).json()
    await settle(app, run2["id"])
    cancelled = (await client.post(f"/api/workflow-runs/{run2['id']}/cancel")).json()
    assert cancelled["status"] == "CANCELLED"
    assert (await client.post(f"/api/workflow-runs/{run2['id']}/retry")).status_code == 409


# ------------------------------------------------------------------ schedules


async def test_schedule_preview_and_crud(client: httpx.AsyncClient, project_id: str) -> None:
    preview = (
        await client.get(
            "/api/schedules/preview", params={"cron": "0 9 * * 1-5", "timezone": "Europe/London"}
        )
    ).json()
    assert preview["description"] == "Weekdays at 09:00" and len(preview["next_runs"]) == 5
    assert (await client.get("/api/schedules/preview", params={"cron": "0 9 * *"})).status_code == 422
    assert (
        await client.get("/api/schedules/preview", params={"cron": "0 9 * * *", "timezone": "Nowhere/Land"})
    ).status_code == 422

    wf = (
        await client.post(
            "/api/workflows",
            json={
                "name": "Daily",
                "project_id": project_id,
                "definition": flow({"x": "inputs.n"}, [{"name": "n", "type": "number"}]),
            },
        )
    ).json()
    bad_inputs = await client.post("/api/schedules", json={"workflow_id": wf["id"], "cron": "0 9 * * *"})
    assert bad_inputs.status_code == 422 and "'n' is required" in bad_inputs.text
    sch = (
        await client.post(
            "/api/schedules", json={"workflow_id": wf["id"], "cron": "0 9 * * *", "inputs": {"n": "4"}}
        )
    ).json()
    assert sch["inputs"] == {"n": 4} and sch["description"] == "Every day at 09:00" and sch["next_run_at"]
    off = (await client.patch(f"/api/schedules/{sch['id']}", json={"enabled": False})).json()
    assert off["enabled"] is False and off["next_run_at"] is None
    on = (
        await client.patch(f"/api/schedules/{sch['id']}", json={"enabled": True, "cron": "30 7 * * mon"})
    ).json()
    assert on["description"] == "Every Monday at 07:30" and on["next_run_at"]
    assert [
        s["id"] for s in (await client.get("/api/schedules", params={"workflow_id": wf["id"]})).json()
    ] == [sch["id"]]
    assert (await client.delete(f"/api/schedules/{sch['id']}")).status_code == 204
    assert (await client.get("/api/schedules")).json() == []


async def test_the_scheduler_fires_due_schedules_once_unattended(
    app: FastAPI, client: httpx.AsyncClient, project_id: str
) -> None:
    c: AppContainer = app.state.container
    wf = (
        await client.post(
            "/api/workflows",
            json={"name": "Hourly", "project_id": project_id, "definition": flow({"x": "1"})},
        )
    ).json()
    sch = (await client.post("/api/schedules", json={"workflow_id": wf["id"], "cron": "0 * * * *"})).json()
    due = datetime.fromisoformat(sch["next_run_at"]).replace(tzinfo=UTC)

    assert await c.scheduler.tick(due - timedelta(minutes=1)) == []  # not yet
    # the app was closed for a day: missed hours collapse into one run
    started = await c.scheduler.tick(due + timedelta(hours=26, minutes=5))
    assert len(started) == 1
    run = await c.workflows.wait_for(started[0])
    assert run.unattended and run.schedule_id == sch["id"] and run.status.value == "COMPLETED"
    after = (await client.get("/api/schedules")).json()[0]
    assert after["last_run_id"] == run.id and after["last_status"] == "COMPLETED"
    assert datetime.fromisoformat(after["next_run_at"]).replace(tzinfo=UTC) > due + timedelta(hours=26)
    types = [e["type"] for e in (await client.get("/api/events", params={"limit": 200})).json()]
    assert "SCHEDULE_FIRED" in types and "WORKFLOW_STARTED" in types


async def test_the_scheduler_skips_rather_than_piling_up(
    app: FastAPI, client: httpx.AsyncClient, project_id: str
) -> None:
    c: AppContainer = app.state.container
    gated = (
        await client.post(
            "/api/workflows",
            json={"name": "Slow", "project_id": project_id, "definition": flow({"x": "1"}, gate=True)},
        )
    ).json()
    sch = (
        await client.post("/api/schedules", json={"workflow_id": gated["id"], "cron": "*/5 * * * *"})
    ).json()
    t = datetime.fromisoformat(sch["next_run_at"]).replace(tzinfo=UTC)
    [first] = await c.scheduler.tick(t)
    assert (await c.workflows.wait_for(first)).status.value == "WAITING"
    assert await c.scheduler.tick(t + timedelta(minutes=5)) == []  # the previous run still waits: skipped
    skipped = [
        e
        for e in (await client.get("/api/events", params={"limit": 200})).json()
        if e["type"] == "SCHEDULE_SKIPPED"
    ]
    assert skipped and "still going" in skipped[0]["payload"]["reason"]
    # run-now ignores the overlap rule (the person asked)
    manual = (await client.post(f"/api/schedules/{sch['id']}/run-now")).json()
    assert manual["last_run_id"] != first

    await client.put(f"/api/workflows/{gated['id']}", json={"enabled": False})
    await c.workflows.cancel(first)
    await c.workflows.cancel(manual["last_run_id"])
    assert await c.scheduler.tick(t + timedelta(minutes=20)) == []  # the workflow is turned off
    await client.delete(f"/api/workflows/{gated['id']}")
    assert await c.scheduler.tick(t + timedelta(minutes=40)) == []
    gone = (await client.get("/api/schedules")).json()[0]
    assert gone["enabled"] is False and gone["last_status"] == "WORKFLOW_GONE"
