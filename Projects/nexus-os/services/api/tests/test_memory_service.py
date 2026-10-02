"""MemoryService against a real database: the write path, recall, privacy, editing, forgetting, compression."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI

from app.core.clock import ManualClock
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.memory.embedder import HashingEmbedder
from app.memory.service import MemoryService
from app.repositories.events import EventFilter
from app.repositories.memory_store import MemoryFilter, MemoryStore
from app.schemas.memory import MemoryCreate, MemorySource, MemoryUpdate
from app.schemas.projects import ProjectCreate
from app.services.container import AppContainer

AGENT = MemorySource(kind="agent", agent="researcher", run_id="run_1")
USER = MemorySource(kind="user")


@dataclass
class MS:
    c: AppContainer
    svc: MemoryService
    store: MemoryStore
    clock: ManualClock
    project_id: str

    async def remember(self, text: str, source: MemorySource = AGENT, **kw: object):  # type: ignore[no-untyped-def]
        kw.setdefault("scope", "project")
        kw.setdefault("project_id", self.project_id)
        return await self.svc.propose(text, source=source, **kw)  # type: ignore[arg-type]

    async def events(self, *types: str) -> list[dict[str, object]]:
        found = await self.c.bus.query(EventFilter(), limit=500)
        return [e.payload for e in found if e.type in types]

    async def recall(self, q: str, **kw: object) -> list[str]:
        kw.setdefault("project_id", self.project_id)
        return [h.item.content for h in await self.svc.search(q, **kw)]  # type: ignore[arg-type]


@pytest.fixture
async def ms(app: FastAPI) -> AsyncIterator[MS]:
    c: AppContainer = app.state.container
    clock = ManualClock(datetime(2026, 9, 29, 9, tzinfo=UTC))
    store = MemoryStore(c.db, clock)
    svc = MemoryService(store, c.search_index, c.bus, HashingEmbedder(), clock)
    project = await c.projects.create(ProjectCreate(name="Memory Tests"))
    yield MS(c, svc, store, clock, project.id)


async def test_a_memory_is_stored_embedded_indexed_and_announced(ms: MS) -> None:
    result = await ms.remember("The client prefers British spelling.", tags=["Style", "style", " "])
    assert result.action == "created" and result.item is not None
    item = result.item
    assert (item.status, item.scope, item.importance, item.tags) == ("active", "project", 0.5, ["style"])
    assert item.source.agent == "researcher" and item.source.run_id == "run_1"
    [created] = await ms.events("MEMORY_CREATED")
    assert created["id"] == item.id and created["preview"] == item.content and created["source"] == "agent"
    hits = await ms.c.search_index.query("british spelling", kinds=["memory"])
    assert [h.ref_id for h in hits] == [item.id]
    assert await ms.recall("Which spelling should documents use?") == [item.content]


async def test_sensitive_content_is_refused_and_only_the_category_is_recorded(ms: MS) -> None:
    secret = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"
    result = await ms.remember(f"The Anthropic key is {secret}, use it for the demo.")
    assert result.action == "rejected" and result.item is None and result.categories == ["API key"]
    assert "sensitive" in result.message and secret not in result.message
    assert await ms.store.list_items(MemoryFilter(statuses=("active", "pending", "deleted"))) == []
    [rejected] = await ms.events("MEMORY_REJECTED")
    assert rejected["categories"] == ["API key"]
    everything = json.dumps([e.payload for e in await ms.c.bus.query(EventFilter(), limit=500)])
    assert secret not in everything and "sk-ant" not in everything
    with pytest.raises(InvalidRequestError, match="payment card number"):
        await ms.svc.create_by_user(
            MemoryCreate(
                scope="project", project_id=ms.project_id, content="Card 4111 1111 1111 1111 for travel"
            )
        )


async def test_exact_duplicates_are_reused_not_repeated(ms: MS) -> None:
    first = (await ms.remember("Invoices go out on the first Monday.", tags=["billing"])).item
    again = await ms.remember("  invoices go out on the FIRST Monday.  ", tags=["dates"], source=USER)
    assert again.action == "duplicate" and again.item is not None and first is not None
    assert again.item.id == first.id
    assert again.item.importance == 0.8 and again.item.tags == [
        "billing",
        "dates",
    ]  # max importance, union of tags
    assert len(await ms.store.list_items(MemoryFilter())) == 1


async def test_near_duplicates_merge_but_never_rewrite_the_persons_own_words(ms: MS) -> None:
    first = (await ms.remember("Deploy with the staging checklist before every production release.")).item
    merged = await ms.remember(
        "Deploy with the staging checklist before every production release!", tags=["deploy"]
    )
    assert merged.action == "merged" and merged.item is not None and first is not None
    assert merged.item.id == first.id and merged.item.content.endswith("release!")
    assert "MEMORY_UPDATED" in [e for e in [ev.type for ev in await ms.c.bus.query(EventFilter(), limit=100)]]

    mine = (await ms.remember("Our brand colours are teal and coral, never neon.", source=USER)).item
    theirs = await ms.remember("Our brand colours are teal and coral, never neon!!")
    assert theirs.action == "duplicate" and theirs.item is not None and mine is not None
    assert theirs.item.id == mine.id and theirs.item.content == mine.content  # unchanged
    assert len(await ms.store.list_items(MemoryFilter())) == 2


async def test_agent_global_memory_waits_for_the_person(ms: MS) -> None:
    proposed = (await ms.remember("The person works in the Europe/London time zone.", scope="global")).item
    assert proposed is not None and proposed.status == "pending" and proposed.project_id is None
    assert await ms.recall("What time zone is the person in?") == []  # pending is never recalled
    with pytest.raises(ConflictError):
        await ms.svc.confirm((await ms.remember("Ships on Fridays.")).item.id)  # type: ignore[union-attr]
    await ms.svc.confirm(proposed.id)
    assert await ms.recall("What time zone is the person in?") == [proposed.content]
    # a person's own global memory is active at once
    own = await ms.svc.create_by_user(MemoryCreate(scope="global", content="I prefer concise answers."))
    assert own.status == "active" and own.importance == 0.8


async def test_private_memories_stay_with_private_runs(ms: MS) -> None:
    private = MemorySource(kind="agent", agent="writer", private=True)
    kept = (await ms.remember("The unreleased product is code-named Heron.", source=private)).item
    assert kept is not None and kept.source.private
    assert await ms.recall("What is the product code name?") == []
    assert await ms.recall("What is the product code name?", include_private=True) == [kept.content]
    # a shareable note that nearly duplicates a private one does not merge into it (or vice versa)
    shared = await ms.remember("The unreleased product is code-named Heron!")
    assert shared.action == "created" and shared.item is not None and shared.item.id != kept.id


async def test_recall_reinforces_only_when_an_agent_uses_it(ms: MS) -> None:
    item = (await ms.remember("Reports are delivered as Markdown with a summary first.")).item
    assert item is not None
    await ms.svc.search("How are reports delivered?", project_id=ms.project_id, touch=False)
    assert (await ms.svc.get(item.id)).access_count == 0
    ms.clock.advance(hours=1)
    await ms.svc.search("How are reports delivered?", project_id=ms.project_id)
    got = await ms.svc.get(item.id)
    assert got.access_count == 1 and got.last_accessed_at == ms.clock.now()


async def test_editing_pinning_and_the_sensitivity_check_on_edits(ms: MS) -> None:
    item = (await ms.remember("Meetings are on Tuesdays.")).item
    assert item is not None
    edited = await ms.svc.update(
        item.id, MemoryUpdate(content="Meetings moved to Thursdays at 10:00.", pinned=True)
    )
    assert edited.content.startswith("Meetings moved") and edited.importance == 1.0 and edited.pinned
    assert await ms.recall("When are the meetings on Thursday?") == [edited.content]
    assert [p.id for p in await ms.svc.pinned(ms.project_id)] == [item.id]
    unpinned = await ms.svc.update(item.id, MemoryUpdate(pinned=False))
    assert unpinned.importance == 0.5
    with pytest.raises(InvalidRequestError, match="password or secret"):
        await ms.svc.update(item.id, MemoryUpdate(content="Meeting room password: swordfish123"))
    assert (await ms.svc.get(item.id)).content == edited.content


async def test_forgetting_is_recoverable_until_purged(ms: MS) -> None:
    item = (await ms.remember("The staging server is called Kestrel.")).item
    assert item is not None
    await ms.svc.delete(item.id)
    assert (await ms.svc.get(item.id)).status == "deleted"
    assert await ms.recall("What is the staging server called?") == []
    assert await ms.c.search_index.query("kestrel") == []
    with pytest.raises(ConflictError):
        await ms.svc.update(item.id, MemoryUpdate(pinned=True))
    await ms.svc.restore(item.id)
    assert await ms.recall("What is the staging server called?") == [item.content]
    await ms.svc.purge(item.id)
    with pytest.raises(NotFoundError):
        await ms.svc.get(item.id)
    assert await ms.c.search_index.query("kestrel") == []
    assert [e["reason"] for e in await ms.events("MEMORY_DELETED")] == ["deleted", "purged"]


async def test_old_related_notes_compress_into_a_summary_that_can_be_undone(ms: MS) -> None:
    old = [
        "Invoices are sent on the first Monday. The client pays within 14 days.",
        "Invoice reminders go out after 14 days. The client pays by bank transfer.",
        "Invoices use the blue template. The client asked for PDF invoices.",
    ]
    originals = [(await ms.remember(t)).item for t in old]
    await ms.remember("The logo is teal.")  # old but unrelated: stays
    pinned = (
        await ms.remember("Invoices are always in euros.", source=USER)
    ).item  # the person's: too important
    ms.clock.advance(days=40)
    await ms.remember("Invoices now include a QR code.")  # related but recent: stays
    report = await ms.svc.compress(ms.project_id)
    assert (report.groups, report.compressed) == (1, 3)
    summary = await ms.svc.get(report.summaries[0])
    assert summary.content.startswith("Summary of 3 older notes:") and summary.source.kind == "summary"
    for o in originals:
        assert o is not None
        gone = await ms.svc.get(o.id)
        assert gone.status == "deleted" and gone.merged_into == summary.id
    live = {i.content for i in await ms.store.list_items(MemoryFilter())}
    assert (
        "The logo is teal." in live
        and "Invoices now include a QR code." in live
        and pinned
        and pinned.content in live
    )
    assert (await ms.events("MEMORY_COMPRESSED"))[0]["merged"] == 3

    restored = await ms.svc.undo_compression(summary.id)
    assert {r.content for r in restored} == set(old)
    assert (await ms.svc.get(summary.id)).status == "deleted"
    assert all(r.status == "active" and r.merged_into is None for r in restored)


async def test_finished_objectives_suggest_a_memory(ms: MS) -> None:
    proposal = await ms.svc.suggest_from_objective(
        project_id=ms.project_id,
        objective_id="obj_1",
        objective="Compare three note apps",
        verdict="PASS",
        summary="The report compares all three and recommends Beta.",
        deliverables=["notes-comparison.md"],
    )
    assert proposal is not None and proposal.item is not None
    item = proposal.item
    assert (
        item.status == "pending" and item.source.kind == "objective" and item.source.objective_id == "obj_1"
    )
    assert (
        "recommends Beta" in item.content
        and "notes-comparison.md" in item.content
        and item.tags == ["objective"]
    )
    assert (
        await ms.svc.suggest_from_objective(
            project_id=ms.project_id, objective_id="obj_2", objective="x", verdict="FAIL", summary="  "
        )
        is None
    )


async def test_stale_vectors_are_re_embedded(ms: MS) -> None:
    item = (await ms.remember("Backups run nightly at 02:00.")).item
    assert item is not None
    await ms.store.set_embedding(item.id, "some-other-embedder", [1.0, 0.0])
    assert await ms.recall("When do backups run nightly?") == [item.content]  # keyword match still works
    assert await ms.svc.reembed_stale() == 1
    [cand] = await ms.store.candidates(MemoryFilter())
    assert cand.embedder == HashingEmbedder().name and len(cand.vector or []) == 256
    assert await ms.svc.reembed_stale() == 0


async def test_validation(ms: MS) -> None:
    with pytest.raises(InvalidRequestError):
        await ms.remember("  ")
    with pytest.raises(InvalidRequestError):
        await ms.svc.propose("A fact", scope="project", project_id=None, source=AGENT)
