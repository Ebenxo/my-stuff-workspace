"""Memory and universal search over HTTP, plus the memory suggestion an objective leaves behind."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.schemas.memory import MemorySource
from app.services.container import AppContainer
from tests.agent_helpers import call, finish
from tests.objective_helpers import OE, make_oe, plan, verdict


@pytest.fixture
async def project_id(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/projects", json={"name": "Garden Centre Site", "description": "Seasonal plant shop"}
    )
    return str(r.json()["id"])


async def test_create_list_search_edit_and_forget(client: httpx.AsyncClient, project_id: str) -> None:
    r = await client.post(
        "/api/memory",
        json={
            "project_id": project_id,
            "content": "The owner wants a calm green palette.",
            "tags": ["Design"],
        },
    )
    assert r.status_code == 201
    item = r.json()
    assert item["status"] == "active" and item["source"]["kind"] == "user" and item["tags"] == ["design"]

    listed = (await client.get("/api/memory", params={"project_id": project_id})).json()
    assert [i["id"] for i in listed] == [item["id"]]
    assert (await client.get("/api/memory", params={"project_id": project_id, "q": "palette"})).json()[0][
        "id"
    ] == item["id"]
    assert (await client.get("/api/memory", params={"project_id": project_id, "tag": "DESIGN"})).json()[0][
        "id"
    ] == item["id"]
    assert (
        await client.get("/api/memory", params={"project_id": project_id, "source": "agent"})
    ).json() == []

    hits = (
        await client.get(
            "/api/memory/search", params={"q": "which colour palette?", "project_id": project_id}
        )
    ).json()
    assert hits[0]["item"]["id"] == item["id"]
    assert set(hits[0]["score"]) == {"semantic", "keyword", "recency", "importance", "task", "total"}
    assert (await client.get(f"/api/memory/{item['id']}")).json()["access_count"] == 0  # browsing is not use

    pinned = (await client.patch(f"/api/memory/{item['id']}", json={"pinned": True})).json()
    assert pinned["importance"] == 1.0
    assert (await client.delete(f"/api/memory/{item['id']}")).status_code == 204
    assert (
        await client.get("/api/memory", params={"project_id": project_id, "status_filter": "deleted"})
    ).json()[0]["id"] == item["id"]
    assert (await client.post(f"/api/memory/{item['id']}/restore")).json()["status"] == "active"
    assert (await client.delete(f"/api/memory/{item['id']}", params={"purge": True})).status_code == 204
    assert (await client.get(f"/api/memory/{item['id']}")).status_code == 404


async def test_refusals_and_validation(client: httpx.AsyncClient, project_id: str) -> None:
    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"
    r = await client.post("/api/memory", json={"project_id": project_id, "content": f"Deploy token {secret}"})
    assert r.status_code == 422 and "access token" in r.text and secret not in r.text
    assert (
        await client.post("/api/memory", json={"project_id": "proj_missing", "content": "A fact"})
    ).status_code == 404
    assert (await client.post("/api/memory", json={"content": "x"})).status_code == 422
    assert (
        await client.post("/api/memory", json={"project_id": project_id, "content": "ok fact", "extra": 1})
    ).status_code == 422


async def test_suggestions_are_confirmed_or_dismissed(
    app: FastAPI, client: httpx.AsyncClient, project_id: str
) -> None:
    c: AppContainer = app.state.container
    a = await c.memory.propose(
        "Works across projects: weekly status on Fridays.",
        scope="global",
        project_id=None,
        source=MemorySource(kind="agent"),
    )
    b = await c.memory.propose(
        "Use metric units everywhere.", scope="global", project_id=None, source=MemorySource(kind="agent")
    )
    assert a.item and b.item
    stats = (await client.get("/api/memory/stats")).json()
    assert stats == {"active": 0, "pending": 2, "deleted": 0}
    assert (await client.post(f"/api/memory/{a.item.id}/confirm")).json()["status"] == "active"
    assert (await client.post(f"/api/memory/{b.item.id}/dismiss")).json()["status"] == "deleted"
    assert (await client.post(f"/api/memory/{a.item.id}/confirm")).status_code == 409
    assert (await client.get("/api/memory/stats")).json() == {"active": 1, "pending": 0, "deleted": 1}


async def test_compress_endpoint(client: httpx.AsyncClient, project_id: str) -> None:
    r = await client.post("/api/memory/compress", json={"project_id": project_id, "older_than_days": 0})
    assert r.status_code == 200 and r.json() == {
        "project_id": project_id,
        "groups": 0,
        "compressed": 0,
        "summaries": [],
    }
    assert (await client.post("/api/memory/compress", json={"project_id": "proj_x"})).status_code == 404


async def test_universal_search_finds_projects_objectives_deliverables_and_memory(
    app: FastAPI, client: httpx.AsyncClient, project_id: str
) -> None:
    c: AppContainer = app.state.container
    await client.post(
        "/api/memory", json={"project_id": project_id, "content": "Succulents need little water."}
    )
    await c.artifacts.save(
        project_id=project_id,
        name="care-guide.md",
        type_="markdown",
        content="# Care guide\nWater succulents monthly.",
    )
    other = (await client.post("/api/projects", json={"name": "Bakery"})).json()["id"]
    await client.post("/api/memory", json={"project_id": other, "content": "Sourdough needs a warm kitchen."})

    everything = (await client.get("/api/search", params={"q": "succulents"})).json()
    assert everything["engine"] == "fts5"
    kinds = {h["kind"]: h for h in everything["hits"]}
    assert set(kinds) == {"memory", "artifact"}
    assert kinds["artifact"]["title"] == "care-guide.md" and "[" in kinds["artifact"]["snippet"]

    garden = (await client.get("/api/search", params={"q": "garden"})).json()["hits"]
    assert [(h["kind"], h["id"]) for h in garden] == [("project", project_id)]
    only_memory = (await client.get("/api/search", params={"q": "need", "kinds": ["memory"]})).json()["hits"]
    assert {h["project_id"] for h in only_memory} == {project_id, other}
    scoped = (await client.get("/api/search", params={"q": "need", "project_id": other})).json()["hits"]
    assert [h["project_id"] for h in scoped] == [other]
    # prefix match on the last word, and FTS syntax typed by a person is treated as text
    assert (await client.get("/api/search", params={"q": "sourdo"})).json()["hits"]
    for odd in ['"unbalanced', "a OR b*", "NEAR(x y)", "-", "col:value"]:
        assert (await client.get("/api/search", params={"q": odd})).status_code == 200
    # renaming a project re-indexes it
    await client.patch(f"/api/projects/{other}", json={"name": "Patisserie"})
    assert (await client.get("/api/search", params={"q": "patisserie"})).json()["hits"][0]["id"] == other
    # the LIKE fallback (SQLite without FTS5) finds the same things
    c.search_index._fts = False
    fallback = (await client.get("/api/search", params={"q": "succulents water"})).json()
    assert fallback["engine"] == "like" and {h["kind"] for h in fallback["hits"]} == {"memory", "artifact"}


async def test_the_index_is_rebuilt_when_empty(
    app: FastAPI, client: httpx.AsyncClient, project_id: str
) -> None:
    c: AppContainer = app.state.container
    await client.post("/api/memory", json={"project_id": project_id, "content": "Opening hours are 9 to 5."})
    await c.search_index.clear()
    assert (await client.get("/api/search", params={"q": "opening"})).json()["hits"] == []
    await c.universal_search.ensure_built()
    assert {h["kind"] for h in (await client.get("/api/search", params={"q": "opening"})).json()["hits"]} == {
        "memory"
    }
    assert {h["kind"] for h in (await client.get("/api/search", params={"q": "garden"})).json()["hits"]} == {
        "project"
    }


# ------------------------------------------------------------------ objectives leave a suggestion


@pytest.fixture
async def oe(app: FastAPI) -> AsyncIterator[OE]:
    env = await make_oe(app)
    yield env
    await env.c.objective_service.shutdown()
    env.c.orchestrator.shutting_down = env.c.runner.shutting_down = False


async def test_a_completed_objective_suggests_remembering_its_outcome(
    oe: OE, client: httpx.AsyncClient
) -> None:
    oe.book.add(
        "Planner", plan([{"key": "t1", "title": "Write the brief", "agent": "writer"}], ["A brief exists"])
    )
    oe.book.add(
        "Writer",
        call("create_markdown", {"name": "brief.md", "content": "# Brief"}),
        finish("Wrote brief.md"),
    )
    oe.book.add(
        "Verifier", verdict("PASS", [("A brief exists", True)], summary="The brief exists and is complete.")
    )
    obj = await oe.wait((await oe.create()).id)
    assert obj.status.value == "COMPLETED"
    [suggestion] = (
        await client.get("/api/memory", params={"project_id": oe.project_id, "status_filter": "pending"})
    ).json()
    assert suggestion["source"] == {**suggestion["source"], "kind": "objective", "objective_id": obj.id}
    assert (
        "The brief exists and is complete." in suggestion["content"] and "brief.md" in suggestion["content"]
    )
    # every run in the objective kept a context report
    tasks = await oe.tasks(obj.id)
    detail = (await client.get(f"/api/runs/{tasks['t1'].run_id}")).json()
    assert detail["context"] is not None and detail["context"]["budget_tokens"] > 0
