"""Ideas, notes and to-dos over HTTP; due reminders; starting an idea as an objective; the timeline; and
paging back through history."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.services.container import AppContainer
from tests.objective_helpers import OE, make_oe, plan


@pytest.fixture
async def project_id(client: httpx.AsyncClient) -> str:
    return str((await client.post("/api/projects", json={"name": "Garden"})).json()["id"])


def at(**delta: float) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


async def add(client: httpx.AsyncClient, **body: Any) -> dict[str, Any]:
    r = await client.post("/api/ideas", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def ids(client: httpx.AsyncClient, **params: Any) -> list[str]:
    r = await client.get("/api/ideas", params=params)
    assert r.status_code == 200, r.text
    return [i["id"] for i in r.json()]


async def events_of(client: httpx.AsyncClient, *types: str) -> list[dict[str, Any]]:
    r = await client.get("/api/events", params={"types": ",".join(types), "limit": 1000})
    return list(r.json())


# ------------------------------------------------------------------ ideas


async def test_capture_validate_list_and_order(client: httpx.AsyncClient, project_id: str) -> None:
    idea = await add(client, text="  Try a darker sidebar  ")
    assert idea["text"] == "Try a darker sidebar"
    assert (idea["kind"], idea["status"], idea["pinned"], idea["due_at"]) == ("idea", "open", False, None)

    for bad in (
        {"text": "   "},
        {"text": "x" * 4001},
        {"text": "x", "kind": "task"},
        {"text": "x", "due_at": "2026-10-02T09:00:00"},  # no timezone: rejected, never guessed
        {"text": "x", "colour": "red"},
    ):
        assert (await client.post("/api/ideas", json=bad)).status_code == 422, bad
    assert (await client.post("/api/ideas", json={"text": "x", "project_id": "prj_nope"})).status_code == 404

    later = await add(client, text="Repot the fern", kind="todo", due_at=at(days=3))
    soon = await add(client, text="Water the basil", kind="todo", due_at=at(days=1), project_id=project_id)
    pinned = await add(client, text="Ask about 50% off seeds", kind="note", pinned=True)

    # Pinned first, then by due date (soonest first), then undated newest first.
    assert await ids(client) == [pinned["id"], soon["id"], later["id"], idea["id"]]
    assert await ids(client, kind="todo") == [soon["id"], later["id"]]
    assert await ids(client, project_id=project_id) == [soon["id"]]
    assert await ids(client, pinned=True) == [pinned["id"]]
    assert await ids(client, q="DARKER") == [idea["id"]]
    assert await ids(client, q="50%") == [pinned["id"]]  # LIKE wildcards are matched literally
    assert await ids(client, q="%") == [pinned["id"]]
    assert await ids(client, q="_") == []
    assert (await client.get("/api/ideas", params={"kind": "task"})).status_code == 422


async def test_update_done_clear_and_delete(client: httpx.AsyncClient, project_id: str) -> None:
    todo = await add(client, text="Order compost", kind="todo", due_at=at(days=2), project_id=project_id)

    done = (await client.patch(f"/api/ideas/{todo['id']}", json={"status": "done"})).json()
    assert done["status"] == "done" and done["done_at"]
    assert await ids(client) == []
    assert await ids(client, status_filter="done") == [todo["id"]]
    assert await ids(client, status_filter="all") == [todo["id"]]

    reopened = (await client.patch(f"/api/ideas/{todo['id']}", json={"status": "open"})).json()
    assert reopened["status"] == "open" and reopened["done_at"] is None

    cleared = (
        await client.patch(f"/api/ideas/{todo['id']}", json={"due_at": None, "project_id": None})
    ).json()
    assert cleared["due_at"] is None and cleared["project_id"] is None

    unchanged = (await client.patch(f"/api/ideas/{todo['id']}", json={})).json()
    assert unchanged["updated_at"] == cleared["updated_at"]

    edited = (
        await client.patch(
            f"/api/ideas/{todo['id']}", json={"text": "Order two bags of compost", "pinned": True}
        )
    ).json()
    assert edited["text"] == "Order two bags of compost" and edited["pinned"] is True
    assert (await client.patch(f"/api/ideas/{todo['id']}", json={"text": ""})).status_code == 422
    assert (
        await client.patch(f"/api/ideas/{todo['id']}", json={"project_id": "prj_nope"})
    ).status_code == 404
    assert (await client.patch("/api/ideas/idea_nope", json={"pinned": True})).status_code == 404

    assert (await client.delete(f"/api/ideas/{todo['id']}")).status_code == 204
    assert (await client.get(f"/api/ideas/{todo['id']}")).status_code == 404
    assert (await client.delete(f"/api/ideas/{todo['id']}")).status_code == 404

    created, updated, deleted = (
        await events_of(client, "IDEA_CREATED"),
        await events_of(client, "IDEA_UPDATED"),
        await events_of(client, "IDEA_DELETED"),
    )
    assert len(created) == 1 and len(deleted) == 1
    assert [e["payload"]["changed"] for e in updated] == [
        ["done_at", "status"],
        ["done_at", "status"],
        ["due_at", "project_id"],
        ["pinned", "text"],
    ]
    assert created[0]["project_id"] == project_id and created[0]["actor"] == "user"


async def test_event_payloads_never_carry_secrets(client: httpx.AsyncClient) -> None:
    key = "sk-ant-" + "q" * 30
    idea = await add(client, text=f"Rotate the key {key} on Friday\nsecond line stays out")
    assert key in idea["text"]  # the person's own note is kept as written
    (created,) = await events_of(client, "IDEA_CREATED")
    assert key not in str(created["payload"]) and "[REDACTED:anthropic_key]" in created["payload"]["text"]
    assert "second line" not in created["payload"]["text"]


async def test_ideas_are_in_universal_search(client: httpx.AsyncClient, project_id: str) -> None:
    idea = await add(client, text="Succulent wall by the window", project_id=project_id)
    hits = (await client.get("/api/search", params={"q": "succulent", "kinds": ["idea"]})).json()["hits"]
    assert [(h["kind"], h["id"], h["project_id"]) for h in hits] == [("idea", idea["id"], project_id)]

    await client.patch(f"/api/ideas/{idea['id']}", json={"status": "done"})
    hits = (await client.get("/api/search", params={"q": "succulent"})).json()["hits"]
    assert hits[0]["title"].endswith("(done)")

    await client.delete(f"/api/ideas/{idea['id']}")
    assert (await client.get("/api/search", params={"q": "succulent"})).json()["hits"] == []


async def test_rebuilding_the_search_index_includes_ideas(app: FastAPI, client: httpx.AsyncClient) -> None:
    c: AppContainer = app.state.container
    await add(client, text="Moss terrarium kit")
    await c.search_index.clear()
    assert await c.universal_search.rebuild() >= 1
    hits = (await client.get("/api/search", params={"q": "terrarium"})).json()["hits"]
    assert [h["kind"] for h in hits] == ["idea"]


# ------------------------------------------------------------------ reminders


async def test_due_items_get_exactly_one_reminder(app: FastAPI, client: httpx.AsyncClient) -> None:
    c: AppContainer = app.state.container
    due = await add(client, text="Call the nursery", kind="todo", due_at=at(minutes=-5))
    await add(client, text="Not yet", kind="todo", due_at=at(days=1))
    finished = await add(client, text="Already done", kind="todo", due_at=at(minutes=-5))
    await client.patch(f"/api/ideas/{finished['id']}", json={"status": "done"})
    assert (await client.get("/api/ideas/due-count")).json() == {"count": 1}

    await c.scheduler.tick()  # reminders ride on the scheduler's tick
    notes = (await client.get("/api/notifications")).json()
    assert [(n["kind"], n["title"], n["ref"]) for n in notes] == [
        ("idea_due", "To-do due: Call the nursery", {"idea_id": due["id"]})
    ]
    (fired,) = await events_of(client, "IDEA_DUE")
    assert fired["payload"]["idea_id"] == due["id"] and fired["actor"] == "scheduler"
    assert (await client.get(f"/api/ideas/{due['id']}")).json()["reminded_at"]

    await c.scheduler.tick()
    assert len((await client.get("/api/notifications")).json()) == 1  # never twice

    # Moving the due time arms a new reminder.
    moved = (await client.patch(f"/api/ideas/{due['id']}", json={"due_at": at(minutes=-1)})).json()
    assert moved["reminded_at"] is None
    await c.scheduler.tick()
    assert len((await client.get("/api/notifications")).json()) == 2


async def test_a_failing_job_does_not_stop_schedules(app: FastAPI, client: httpx.AsyncClient) -> None:
    c: AppContainer = app.state.container
    calls: list[str] = []

    async def broken(_now: datetime) -> None:
        calls.append("broken")
        raise RuntimeError("boom")

    async def fine(_now: datetime) -> None:
        calls.append("fine")

    c.scheduler._also_on_tick[:0] = [broken]  # type: ignore[attr-defined]
    c.scheduler._also_on_tick.append(fine)  # type: ignore[attr-defined]
    await c.scheduler.tick()
    assert calls == ["broken", "fine"]


# ------------------------------------------------------------------ ideas → objectives


@pytest.fixture
async def oe(app: FastAPI) -> AsyncIterator[OE]:
    env = await make_oe(app)
    yield env
    await env.c.objective_service.shutdown()
    env.c.orchestrator.shutting_down = env.c.runner.shutting_down = False


async def test_start_an_idea_as_an_objective(client: httpx.AsyncClient, oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Draft the guide", "agent": "writer"}]))
    loose = await add(client, text="A beginner's guide to herbs")
    r = await client.post(f"/api/ideas/{loose['id']}/objective", json={})
    assert r.status_code == 409 and "Choose a project" in r.text

    r = await client.post(f"/api/ideas/{loose['id']}/objective", json={"project_id": oe.project_id})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["objective"]["text"] == "A beginner's guide to herbs"
    assert body["objective"]["run_mode"] == "review_plan"
    idea = body["idea"]
    assert idea["objective_id"] == body["objective"]["id"] and idea["status"] == "done"
    assert idea["project_id"] == oe.project_id  # adopts the project it was started in

    again = await client.post(f"/api/ideas/{loose['id']}/objective", json={"project_id": oe.project_id})
    assert again.status_code == 409
    (updated,) = [e for e in await events_of(client, "IDEA_UPDATED") if "objective_id" in e["payload"]]
    assert updated["payload"]["objective_id"] == body["objective"]["id"]
    await oe.wait(body["objective"]["id"])


# ------------------------------------------------------------------ timeline


async def test_timeline_brings_everything_together(app: FastAPI, client: httpx.AsyncClient, oe: OE) -> None:
    c: AppContainer = app.state.container
    pid = oe.project_id
    empty = (await client.get("/api/timeline")).json()
    assert (empty["now"], empty["waiting"], empty["next"], empty["pinned"]) == ([], [], [], [])

    # An objective whose plan waits for review.
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    obj = await oe.create(text="Plan the spring planting\nwith details", run_mode="review_plan")
    await oe.wait(obj.id)

    # A workflow that stops at an approval step, and a schedule for it.
    definition = {
        "inputs": [],
        "nodes": [
            {"id": "start", "type": "trigger"},
            {"id": "gate", "type": "approval", "config": {"message": "Go?"}},
            {"id": "out", "type": "output", "config": {"values": {"ok": "true"}}},
        ],
        "edges": [
            {"id": "e0", "source": "start", "target": "gate"},
            {"id": "e1", "source": "gate", "target": "out"},
        ],
    }
    wf = (
        await client.post(
            "/api/workflows", json={"name": "Weekly check", "project_id": pid, "definition": definition}
        )
    ).json()
    run = (await client.post(f"/api/workflows/{wf['id']}/run", json={"inputs": {}})).json()
    await c.workflows.wait_for(run["id"])
    sch = (await client.post("/api/schedules", json={"workflow_id": wf["id"], "cron": "0 9 * * 1"})).json()

    # Ideas: overdue, due later, pinned without a date, and a plain one that stays off the timeline.
    overdue = await add(client, text="Pay the water bill", kind="todo", due_at=at(hours=-2), project_id=pid)
    later = await add(client, text="Seed swap", kind="todo", due_at=at(days=2), project_id=pid)
    keep = await add(client, text="Mulch keeps roots cool", kind="note", pinned=True)
    await add(client, text="Just a thought")

    t = (await client.get("/api/timeline")).json()
    waiting = {(i["kind"], i["id"]): i for i in t["waiting"]}
    assert waiting[("objective", obj.id)]["title"] == "Plan the spring planting"
    assert waiting[("objective", obj.id)]["detail"] == "The plan is ready for your review."
    assert waiting[("workflow_run", run["id"])]["title"] == "Weekly check is waiting for you"
    assert waiting[("idea", overdue["id"])]["status"] == "OVERDUE"
    assert waiting[("idea", overdue["id"])]["idea_kind"] == "todo"
    assert [i["kind"] for i in t["waiting"]].count("idea") == 1

    nxt = [(i["kind"], i["id"]) for i in t["next"]]
    assert ("idea", later["id"]) in nxt and ("schedule", sch["id"]) in nxt
    starts = [i["at"] for i in t["next"]]
    assert starts == sorted(starts)  # soonest first
    schedule_item = next(i for i in t["next"] if i["kind"] == "schedule")
    assert schedule_item["ref_id"] == wf["id"] and schedule_item["detail"] == "Every Monday at 09:00"
    assert [i["id"] for i in t["pinned"]] == [keep["id"]]
    assert t["now"] == []

    # Scoped to a project: the unscoped note drops out; everything else stays.
    other = (await client.post("/api/projects", json={"name": "Elsewhere"})).json()["id"]
    scoped = (await client.get("/api/timeline", params={"project_id": other})).json()
    assert (scoped["now"], scoped["waiting"], scoped["next"], scoped["pinned"]) == ([], [], [], [])
    mine = (await client.get("/api/timeline", params={"project_id": pid})).json()
    assert mine["pinned"] == [] and len(mine["waiting"]) == len(t["waiting"])

    # A turned-off schedule is not coming up.
    await client.patch(f"/api/schedules/{sch['id']}", json={"enabled": False})
    assert all(i["kind"] != "schedule" for i in (await client.get("/api/timeline")).json()["next"])

    # A pending approval shows up as waiting on the person.
    approval = await c.approval_store.create(
        project_id=pid,
        run_id=None,
        task_id=None,
        agent_id=None,
        tool_name="write_file",
        arguments={"path": "notes.md"},
        reason="Save the planting notes",
        risk_level="MODERATE",
        impact="Writes one file",
    )
    items = {(i["kind"], i["id"]): i for i in (await client.get("/api/timeline")).json()["waiting"]}
    assert items[("approval", approval.id)]["title"] == "Approve “write_file”?"
    assert items[("approval", approval.id)]["detail"] == "Save the planting notes"


# ------------------------------------------------------------------ history paging


async def test_history_pages_backwards_and_can_leave_out_types(client: httpx.AsyncClient) -> None:
    for n in range(5):
        await add(client, text=f"Idea {n}")
    newest = (await client.get("/api/events", params={"newest_first": True, "limit": 3})).json()
    assert len(newest) == 3 and newest[0]["seq"] > newest[1]["seq"] > newest[2]["seq"]
    older = (
        await client.get(
            "/api/events", params={"newest_first": True, "limit": 3, "before_seq": newest[-1]["seq"]}
        )
    ).json()
    assert older and all(e["seq"] < newest[-1]["seq"] for e in older)

    without = (
        await client.get("/api/events", params={"exclude_types": "IDEA_CREATED,SYSTEM_STARTED", "limit": 500})
    ).json()
    assert all(e["type"] not in {"IDEA_CREATED", "SYSTEM_STARTED"} for e in without)
    everything = (await client.get("/api/events", params={"limit": 500})).json()
    assert len(everything) - len(without) == 6  # five ideas and the start-up event
