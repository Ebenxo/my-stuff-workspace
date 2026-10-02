from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI

from app.core.settings import Settings
from app.repositories.events import EventFilter


async def test_create_project_creates_workspace_conversation_and_event(
    client: httpx.AsyncClient, app: FastAPI, settings: Settings
) -> None:
    r = await client.post(
        "/api/projects",
        json={"name": "YouTube Automation", "description": "Weekly content", "icon": "video"},
    )
    assert r.status_code == 201
    project = r.json()
    assert project["slug"] == "youtube-automation"
    assert project["status"] == "active"
    assert project["settings"]["permission_level"] is None

    root = settings.default_workspace_root / "projects" / project["id"]
    for sub in ("files", "artifacts", "memory", "temp", ".trash", ".history"):
        assert (root / sub).is_dir()

    convs = (await client.get(f"/api/projects/{project['id']}/conversations")).json()
    assert [c["title"] for c in convs] == ["Main"]

    events = await app.state.container.bus.query(EventFilter(project_id=project["id"]))
    assert [e.type for e in events] == ["PROJECT_CREATED"]
    assert events[0].actor == "user"


async def test_slugs_are_unique(client: httpx.AsyncClient) -> None:
    slugs = []
    for _ in range(3):
        slugs.append((await client.post("/api/projects", json={"name": "Site!"})).json()["slug"])
    assert slugs == ["site", "site-2", "site-3"]


async def test_update_archive_and_filter(client: httpx.AsyncClient) -> None:
    p = (await client.post("/api/projects", json={"name": "A"})).json()
    r = await client.patch(
        f"/api/projects/{p['id']}",
        json={
            "name": "  Renamed ",
            "settings": {"permission_level": "cautious", "monthly_budget_usd": 5},
        },
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["settings"]["permission_level"] == "cautious"

    assert (await client.post(f"/api/projects/{p['id']}/archive")).json()["status"] == "archived"
    again = await client.post(f"/api/projects/{p['id']}/archive")
    assert again.status_code == 409
    assert [
        x["id"] for x in (await client.get("/api/projects", params={"status_filter": "active"})).json()
    ] == []
    assert len((await client.get("/api/projects", params={"status_filter": "archived"})).json()) == 1
    assert (await client.post(f"/api/projects/{p['id']}/unarchive")).json()["status"] == "active"


async def test_unknown_fields_and_bad_values_rejected(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/projects", json={"name": "x", "surprise": 1})
    assert r.status_code == 422
    r = await client.post("/api/projects", json={"name": "x", "settings": {"permission_level": "yolo"}})
    assert r.status_code == 422
    r = await client.post("/api/projects", json={"name": "x" * 500})
    assert r.status_code == 422


async def test_missing_project_is_404(client: httpx.AsyncClient) -> None:
    for method, url in (("get", "/api/projects/nope"), ("post", "/api/projects/nope/archive")):
        assert (await getattr(client, method)(url)).status_code == 404
    assert (await client.get("/api/projects/nope/conversations")).status_code == 404


async def test_conversations_and_messages(client: httpx.AsyncClient, app: FastAPI) -> None:
    p = (await client.post("/api/projects", json={"name": "Chatty"})).json()
    conv = (await client.post(f"/api/projects/{p['id']}/conversations", json={"title": "Ideas"})).json()
    assert conv["title"] == "Ideas"
    m1 = (await client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "hello"})).json()
    m2 = (await client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "world"})).json()
    assert m1["role"] == "user"
    listed = (await client.get(f"/api/conversations/{conv['id']}/messages")).json()
    assert [m["content"] for m in listed] == ["hello", "world"]
    after = (
        await client.get(f"/api/conversations/{conv['id']}/messages", params={"after_id": m1["id"]})
    ).json()
    assert [m["id"] for m in after] == [m2["id"]]
    assert (
        await client.post(f"/api/conversations/{conv['id']}/messages", json={"content": ""})
    ).status_code == 422
    assert (await client.get("/api/conversations/nope/messages")).status_code == 404
    events = await app.state.container.bus.query(EventFilter(project_id=p["id"]))
    assert [e.type for e in events].count("MESSAGE_CREATED") == 2


async def test_settings_roundtrip_and_workspace_rules(
    client: httpx.AsyncClient, settings: Settings, tmp_path: Path
) -> None:
    s = (await client.get("/api/settings")).json()
    assert s["onboarding_completed"] is False
    assert s["default_permission_level"] == "balanced"
    assert s["workspace_root"] == str(settings.default_workspace_root)

    new_root = tmp_path / "my-workspace"
    r = await client.patch(
        "/api/settings",
        json={
            "display_name": "Ada",
            "default_permission_level": "cautious",
            "workspace_root": str(new_root),
            "preferences": {"theme": "dark"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Ada"
    assert body["default_permission_level"] == "cautious"
    assert body["workspace_root"] == str(new_root.resolve())
    assert new_root.is_dir()

    await client.patch("/api/settings", json={"preferences": {"density": "compact"}})
    assert (await client.get("/api/settings")).json()["preferences"] == {
        "theme": "dark",
        "density": "compact",
    }

    await client.post("/api/projects", json={"name": "Now projects exist"})
    r = await client.patch("/api/settings", json={"workspace_root": str(tmp_path / "elsewhere")})
    assert r.status_code == 409
    same = await client.patch("/api/settings", json={"workspace_root": str(new_root)})
    assert same.status_code == 200


async def test_relative_workspace_root_rejected(client: httpx.AsyncClient) -> None:
    r = await client.patch("/api/settings", json={"workspace_root": "relative/path"})
    assert r.status_code == 422


async def test_notifications_flow(client: httpx.AsyncClient, app: FastAPI) -> None:
    svc = app.state.container.notifications
    n1 = await svc.notify("task_completed", "Done", "body", project_id="proj_x")
    await svc.notify("approval_required", "Needs approval")
    assert (await client.get("/api/notifications/unread-count")).json() == {"count": 2}
    r = await client.post(f"/api/notifications/{n1.id}/read")
    assert r.json()["read_at"] is not None
    assert (await client.get("/api/notifications", params={"unread_only": True})).json()[0][
        "kind"
    ] == "approval_required"
    assert (await client.post("/api/notifications/read-all")).json() == {"marked": 1}
    assert (await client.post("/api/notifications/nope/read")).status_code == 404


async def test_failing_notification_sink_does_not_lose_notification(app: FastAPI) -> None:
    svc = app.state.container.notifications

    class Broken:
        name = "broken"

        async def deliver(self, notification: object) -> None:
            raise RuntimeError("smtp down")

    svc.add_sink(Broken())
    await svc.notify("system_error", "Still recorded")
    assert (await svc.list_all())[0].title == "Still recorded"
