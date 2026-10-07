from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.events.bus import EventBus
from app.events.sse import event_stream
from app.events.types import EventType
from app.repositories.events import EventFilter


def bus_of(app: FastAPI) -> EventBus:
    return app.state.container.bus  # type: ignore[no-any-return]


async def test_events_are_hash_chained_per_project(app: FastAPI) -> None:
    bus = bus_of(app)
    a1 = await bus.emit(EventType.PROJECT_CREATED, project_id="proj_a", payload={"n": 1})
    b1 = await bus.emit(EventType.PROJECT_CREATED, project_id="proj_b", payload={"n": 1})
    a2 = await bus.emit(EventType.TASK_CREATED, project_id="proj_a", payload={"n": 2})
    assert a2.prev_hash == a1.hash
    assert b1.prev_hash != a1.hash  # independent chain
    assert a1.hash != a2.hash
    result = await bus.verify()
    assert result.ok
    assert result.events_checked >= 3


async def test_tampering_is_detected(app: FastAPI) -> None:
    bus = bus_of(app)
    await bus.emit(EventType.TASK_CREATED, project_id="proj_t", payload={"title": "original"})
    victim = await bus.emit(EventType.TASK_COMPLETED, project_id="proj_t", payload={"ok": True})
    await bus.emit(EventType.TASK_CREATED, project_id="proj_t", payload={"title": "later"})
    assert (await bus.verify("proj_t")).ok

    db = app.state.container.db
    async with db.session() as s:
        await s.execute(
            text("UPDATE events SET payload = :p WHERE seq = :seq"),
            {"p": json.dumps({"ok": False}), "seq": victim.seq},
        )
    broken = await bus.verify("proj_t")
    assert not broken.ok
    assert broken.first_bad_seq == victim.seq


async def test_payload_is_redacted_before_persisting(app: FastAPI) -> None:
    bus = bus_of(app)
    rec = await bus.emit(
        EventType.TOOL_CALLED,
        project_id="proj_r",
        payload={"args": {"api_key": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123", "q": "hi"}},
    )
    stored = (await bus.query(EventFilter(project_id="proj_r")))[0]
    assert rec.payload["args"]["api_key"] == "[REDACTED]"
    assert "sk-ant" not in json.dumps(stored.payload)
    assert (await bus.verify("proj_r")).ok


async def test_payload_with_non_json_values_round_trips_and_verifies(app: FastAPI) -> None:
    from datetime import UTC, datetime

    bus = bus_of(app)
    await bus.emit(
        EventType.TASK_CREATED,
        project_id="proj_j",
        payload={"when": datetime(2026, 1, 2, tzinfo=UTC), "t": (1, 2), "n": None, 3: "x"},
    )
    assert (await bus.verify("proj_j")).ok


async def test_query_filters_and_paging(app: FastAPI) -> None:
    bus = bus_of(app)
    for i in range(5):
        await bus.emit(EventType.TASK_CREATED, project_id="proj_q", objective_id="obj_1", payload={"i": i})
    await bus.emit(EventType.TASK_CREATED, project_id="proj_q", objective_id="obj_2")
    first = await bus.query(EventFilter(project_id="proj_q", objective_id="obj_1"), limit=3)
    assert [e.payload["i"] for e in first] == [0, 1, 2]
    rest = await bus.query(EventFilter(project_id="proj_q", objective_id="obj_1"), after_seq=first[-1].seq)
    assert [e.payload["i"] for e in rest] == [3, 4]
    newest = await bus.query(EventFilter(project_id="proj_q"), limit=1, newest_first=True)
    assert newest[0].objective_id == "obj_2"
    typed = await bus.query(EventFilter(project_id="proj_q", types=frozenset({"NOPE"})))
    assert typed == []


async def test_listener_errors_do_not_break_emit(app: FastAPI) -> None:
    bus = bus_of(app)
    seen: list[str] = []

    def bad(_: object) -> None:
        raise RuntimeError("boom")

    async def good(rec: object) -> None:
        seen.append(rec.type)  # type: ignore[attr-defined]

    bus.add_listener(bad)
    bus.add_listener(good)
    await bus.emit(EventType.SYSTEM_ERROR, payload={})
    assert seen == ["SYSTEM_ERROR"]


async def _collect(gen, n: int, wait_s: float = 5.0) -> list[str]:  # type: ignore[no-untyped-def]
    frames: list[str] = []

    async def run() -> None:
        async for frame in gen:
            frames.append(frame)
            if sum(1 for f in frames if f.startswith("id:")) >= n:
                return

    await asyncio.wait_for(run(), wait_s)
    return frames


def _ids(frames: list[str]) -> list[int]:
    return [int(f.split("\n", 1)[0].removeprefix("id: ")) for f in frames if f.startswith("id:")]


async def test_sse_replays_after_last_seen_then_tails_without_gaps_or_dupes(app: FastAPI) -> None:
    bus = bus_of(app)
    flt = EventFilter(project_id="proj_s")
    seeded = [await bus.emit(EventType.TASK_CREATED, project_id="proj_s", payload={"i": i}) for i in range(3)]

    async def produce() -> None:
        await asyncio.sleep(0.05)
        for i in range(3, 6):
            await bus.emit(EventType.TASK_CREATED, project_id="proj_s", payload={"i": i})

    producer = asyncio.create_task(produce())
    frames = await _collect(event_stream(bus, flt, after_seq=seeded[0].seq), n=5)
    await producer
    ids = _ids(frames)
    assert ids == sorted(set(ids)), "no duplicates and in order"
    assert ids[0] == seeded[1].seq
    assert len(ids) == 5
    assert frames[0].startswith("retry:")


async def test_sse_without_after_starts_live_only(app: FastAPI) -> None:
    bus = bus_of(app)
    await bus.emit(EventType.TASK_CREATED, project_id="proj_l", payload={"old": True})
    flt = EventFilter(project_id="proj_l")

    async def produce() -> None:
        await asyncio.sleep(0.05)
        await bus.emit(EventType.TASK_CREATED, project_id="proj_l", payload={"new": True})

    producer = asyncio.create_task(produce())
    frames = await _collect(event_stream(bus, flt), n=1)
    await producer
    data = json.loads(next(f for f in frames if f.startswith("id:")).split("data: ", 1)[1])
    assert data["payload"] == {"new": True}


async def test_sse_heartbeat_when_idle(app: FastAPI) -> None:
    bus = bus_of(app)
    gen = event_stream(bus, EventFilter(project_id="proj_idle"), heartbeat_s=0.05)
    frames = [await anext(gen), await asyncio.wait_for(anext(gen), 2)]
    await gen.aclose()
    assert frames[1] == ": ping\n\n"


async def test_slow_consumer_gets_resync_not_silent_loss(app: FastAPI) -> None:
    bus = bus_of(app)
    bus._queue_size = 2  # tiny queue to force overflow
    flt = EventFilter(project_id="proj_o")
    gen = event_stream(bus, flt)
    await anext(gen)  # retry line; subscription is now open
    task = asyncio.create_task(anext(gen))
    await asyncio.sleep(0.01)
    for i in range(6):
        await bus.emit(EventType.TASK_CREATED, project_id="proj_o", payload={"i": i})
    frames: list[str] = [await asyncio.wait_for(task, 2)]
    async for frame in gen:
        frames.append(frame)
    assert any(f.startswith("event: resync") for f in frames)
    assert bus.subscriber_count == 0


async def test_events_api_list_and_verify(client: httpx.AsyncClient, app: FastAPI) -> None:
    bus = bus_of(app)
    await bus.emit(EventType.TASK_CREATED, project_id="proj_api", payload={"x": 1})
    r = await client.get("/api/events", params={"project_id": "proj_api"})
    assert r.status_code == 200
    assert r.json()[0]["type"] == "TASK_CREATED"
    v = await client.get("/api/events/verify")
    assert v.json()["ok"] is True
    v = await client.get("/api/events/verify", params={"project_id": "proj_api"})
    assert v.json()["events_checked"] == 1
