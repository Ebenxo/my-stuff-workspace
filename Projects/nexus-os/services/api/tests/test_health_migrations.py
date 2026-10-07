from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app import migrate
from app.migrate import include_name
from app.models import Base


async def test_health_report_shape(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    names = {c["name"] for c in body["checks"]}
    assert {"backend", "database", "events", "queue", "disk", "secrets"} <= names
    db = next(c for c in body["checks"] if c["name"] == "database")
    assert db["status"] == "ok"
    assert db["data"]["revision"] == migrate.head_revision(f"sqlite:///{db['data']['path']}")
    secrets = next(c for c in body["checks"] if c["name"] == "secrets")
    assert secrets["status"] == "degraded"  # tests use the in-memory store
    assert body["status"] == "degraded"
    assert "path" in db["data"]  # path is local diagnostic info; ping stays minimal
    assert (await client.get("/api/health/ping")).json() == {"ok": True}


async def test_health_reports_failing_check_as_down(app, client: httpx.AsyncClient) -> None:  # type: ignore[no-untyped-def]
    async def broken():  # type: ignore[no-untyped-def]
        raise RuntimeError("secret internal detail")

    app.state.container.health.register("broken", broken)
    body = (await client.get("/api/health")).json()
    bad = next(c for c in body["checks"] if c["name"] == "broken")
    assert bad["status"] == "down"
    assert "secret internal detail" not in bad["detail"]
    assert body["status"] == "down"


def test_migrations_upgrade_downgrade_and_match_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    migrate.upgrade(url)
    head = migrate.head_revision(url)
    assert migrate.current_revision(url) == head

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    expected = {
        "user_settings",
        "projects",
        "conversations",
        "messages",
        "providers",
        "usage_records",
        "events",
        "notifications",
        "agents",
        "agent_runs",
        "tools",
        "tool_calls",
        "approvals",
        "artifacts",
        "artifact_versions",
        "objectives",
        "tasks",
        "task_dependencies",
        "memory_items",
        "memory_embeddings",
        "search_index",
        "workflows",
        "workflow_versions",
        "workflow_runs",
        "schedules",
        "integrations",
        "ideas",
        "alembic_version",
    }
    assert expected <= tables
    assert head == "0007"

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "include_name": include_name})
        diff = compare_metadata(ctx, Base.metadata)
    engine.dispose()
    assert diff == [], f"models and migrations disagree: {diff}"

    migrate.downgrade(url, "base")
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
    migrate.upgrade(url)  # and back up again
    assert migrate.current_revision(url) == head


def test_foreign_keys_and_wal_enabled(tmp_path: Path) -> None:
    import asyncio

    from sqlalchemy import text

    from app.models.database import Database

    url = f"sqlite:///{(tmp_path / 'p.db').as_posix()}"
    migrate.upgrade(url)

    async def go() -> tuple[int, str]:
        db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'p.db').as_posix()}")
        try:
            async with db.session() as s:
                fk = (await s.execute(text("PRAGMA foreign_keys"))).scalar_one()
                mode = (await s.execute(text("PRAGMA journal_mode"))).scalar_one()
                return int(fk), str(mode)
        finally:
            await db.close()

    fk, mode = asyncio.run(go())
    assert fk == 1
    assert mode.lower() == "wal"


async def test_cascade_delete_removes_messages(app, client: httpx.AsyncClient) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    p = (await client.post("/api/projects", json={"name": "Cascade"})).json()
    conv = (await client.get(f"/api/projects/{p['id']}/conversations")).json()[0]
    await client.post(f"/api/conversations/{conv['id']}/messages", json={"content": "x"})
    db = app.state.container.db
    async with db.session() as s:
        await s.execute(text("DELETE FROM projects WHERE id = :i"), {"i": p["id"]})
    async with db.session() as s:
        n = (await s.execute(text("SELECT count(*) FROM messages"))).scalar_one()
    assert n == 0


@pytest.mark.parametrize("bad", ["", " ", "\t\n", "x" * 121])
async def test_project_name_bounds(client: httpx.AsyncClient, bad: str) -> None:
    r = await client.post("/api/projects", json={"name": bad})
    assert r.status_code == 422


async def test_project_name_is_trimmed(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/projects", json={"name": "  Padded  "})
    assert r.status_code == 201
    assert r.json()["name"] == "Padded"
