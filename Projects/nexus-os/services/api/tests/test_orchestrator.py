from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI

from app.core.errors import ConflictError, InvalidRequestError
from app.schemas.agents import AgentUpdate
from app.schemas.orchestration import ObjectiveRun, ObjectiveStatus, PlanEdit, PlanTask, TaskStatus
from app.schemas.runtime import RunStatus
from tests.objective_helpers import OE, call, finish, make_oe, plan, review, verdict

OBJ = ObjectiveStatus
TS = TaskStatus


@pytest.fixture
async def oe(app: FastAPI) -> AsyncIterator[OE]:
    env = await make_oe(app)
    yield env
    await env.c.objective_service.shutdown()
    env.c.orchestrator.shutting_down = env.c.runner.shutting_down = False


async def write(oe: OE, rel: str, text: str) -> None:
    root = await oe.c.projects.project_dir(oe.project_id)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text)


REPORT_TASKS = [
    {"key": "t1", "title": "Collect facts", "agent": "researcher", "expected_outputs": ["facts"]},
    {"key": "t2", "title": "Write the report", "agent": "writer", "depends_on": ["t1"], "review": True},
]


# ------------------------------------------------------------------ the whole lifecycle


async def test_objective_is_planned_delegated_reviewed_revised_and_verified(oe: OE) -> None:
    oe.book.add(
        "Planner",
        call("list_directory", {"path": "files"}, "Looking at the project"),
        plan(REPORT_TASKS, ["A report comparing three assistants exists"]),
    )
    oe.book.add("Researcher", finish("Facts: Alpha is fast, Beta is accurate, Gamma is cheap"))
    oe.book.add(
        "Writer",
        call("create_markdown", {"name": "report.md", "content": "# Report\nAlpha, Beta"}),
        finish("Wrote report.md"),
    )
    oe.book.add(
        "Critic",
        call("read_file", {"path": "artifacts/report.md"}, "Reading the report itself"),
        review(
            "revise", [{"severity": "major", "description": "Gamma is missing", "suggestion": "Add Gamma"}]
        ),
    )
    oe.book.add(
        "Writer",
        call("create_markdown", {"name": "report.md", "content": "# Report\nAlpha, Beta, Gamma"}),
        finish("Added Gamma"),
    )
    oe.book.add("Critic", review("approve", summary="All three are covered"))
    oe.book.add(
        "Verifier",
        call("read_file", {"path": "artifacts/report.md"}),
        verdict("PASS", [("A report comparing three assistants exists", True)]),
    )

    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.COMPLETED, obj.error
    tasks = await oe.tasks(obj.id)
    assert list(tasks) == ["t1", "t2", "t2-review1", "t2-rev1", "t2-review2", "verify1"]
    assert all(t.status is TS.COMPLETED for t in tasks.values())
    assert (
        tasks["t2-rev1"].kind == "revise"
        and tasks["t2-rev1"].round == 1
        and tasks["t2-rev1"].parent_task_id == tasks["t2"].id
    )
    assert tasks["t2-review2"].parent_task_id == tasks["t2-rev1"].id
    assert oe.book.remaining() == 0

    # work flows through dependencies, as data
    assert oe.book.calls.index(("Writer", 0)) > oe.book.calls.index(("Researcher", 0))
    writer_first = oe.requests_for("Writer")[0]
    assert "Facts: Alpha is fast" in writer_first and '<untrusted id="' in writer_first
    revise = oe.requests_for("Writer")[2]  # the revision run's first call
    assert "Gamma is missing" in revise and "Fix: Add Gamma" in revise and "Wrote report.md" in revise
    critic_first = oe.requests_for("Critic")[0]
    assert (
        "Wrote report.md" in critic_first
        and "## Your result" in critic_first
        and "ReviewResult" in critic_first
    )
    assert "verdict" in oe.requests_for("Verifier")[0]

    # the deliverable kept its history; the objective's result reports the latest version
    arts = await oe.c.artifacts.list_artifacts(project_id=oe.project_id)
    assert [(a.name, a.version) for a in arts] == [("report.md", 2)]
    assert obj.result is not None and obj.result["verdict"] == "PASS"
    assert [(a["name"], a["version"]) for a in obj.result["artifacts"]] == [("report.md", 2)]
    assert obj.strategy is not None and obj.strategy["name"] == "reviewer"

    # everything is observable
    types = await oe.event_types(obj.id)
    for t in (
        "OBJECTIVE_CREATED",
        "PLAN_CREATED",
        "TASK_CREATED",
        "TASK_STARTED",
        "REVIEW_COMPLETED",
        "VERIFICATION_COMPLETED",
        "OBJECTIVE_COMPLETED",
    ):
        assert t in types, t
    assert types.count("REVIEW_COMPLETED") == 2
    detail = await oe.c.objective_service.detail(obj.id)
    kinds = [m.type for m in detail.messages]
    for k in ("TASK_REQUEST", "TASK_RESULT", "REVIEW_REQUEST", "REVIEW_RESULT"):
        assert k in kinds, k
    assert any(m.sender == "critic" and m.recipient == "writer" for m in detail.messages)
    notes = await oe.c.notifications.list_all()
    assert any("complete" in n.title for n in notes)


async def test_a_plan_can_wait_for_review_and_then_run(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write it", "agent": "writer"}], complexity="small"))
    obj = await oe.wait((await oe.create(run_mode="review_plan")).id)
    assert obj.status is OBJ.AWAITING_PLAN_APPROVAL
    assert obj.plan is not None and obj.plan["tasks"][0]["agent"] == "writer"
    assert (
        obj.strategy is not None
        and obj.strategy["name"] == "single_agent"
        and obj.strategy["estimated_tokens"] > 0
    )
    assert [t.status for t in (await oe.tasks(obj.id)).values()] == [TS.WAITING]
    assert not oe.requests_for("Writer")  # nothing ran

    oe.book.add("Writer", finish("Done"))
    oe.book.add("Verifier", verdict("PASS"))
    await oe.c.objective_service.run(obj.id, ObjectiveRun())
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED
    with pytest.raises(ConflictError):
        await oe.c.objective_service.run(obj.id, ObjectiveRun())


async def test_independent_tasks_run_in_parallel(oe: OE) -> None:
    oe.book.add(
        "Planner",
        plan(
            [
                {"key": "a", "title": "Research", "agent": "researcher"},
                {"key": "b", "title": "Analyse", "agent": "data_analyst"},
                {"key": "c", "title": "Write", "agent": "writer", "depends_on": ["a", "b"]},
            ]
        ),
    )
    oe.book.add("Researcher", call("datetime", {}), finish("Research done"))
    oe.book.add("Data Analyst", call("calculator", {"expression": "2*21"}), finish("Analysis done"))
    oe.book.add("Writer", finish("Combined"))
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.COMPLETED and obj.strategy is not None and obj.strategy["name"] == "parallel"
    events = await oe.events(obj.id, "TASK_STARTED", "TASK_COMPLETED")
    seq = [(e.type, e.payload["key"]) for e in events]
    # both branches were started before either finished, and the join waited for both
    assert seq.index(("TASK_STARTED", "b")) < seq.index(("TASK_COMPLETED", "a"))
    assert seq.index(("TASK_STARTED", "a")) < seq.index(("TASK_COMPLETED", "b"))
    assert seq.index(("TASK_STARTED", "c")) > max(
        seq.index(("TASK_COMPLETED", "a")), seq.index(("TASK_COMPLETED", "b"))
    )
    writer = oe.requests_for("Writer")[0]
    assert "Research done" in writer and "Analysis done" in writer


# ------------------------------------------------------------------ planning problems


async def test_an_invalid_plan_gets_one_chance_to_be_fixed(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "x", "agent": "wizard"}]))
    oe.book.add("Planner", plan([{"key": "t1", "title": "x", "agent": "writer"}]))
    obj = await oe.wait((await oe.create(run_mode="review_plan")).id)
    assert obj.status is OBJ.AWAITING_PLAN_APPROVAL
    second = oe.requests_for("Planner")[1]
    assert "could not be used" in second and "unknown agent 'wizard'" in second


async def test_a_plan_that_stays_invalid_fails_honestly(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "x", "agent": "verifier"}]))
    oe.book.add("Planner", plan([{"key": "t1", "title": "x", "agent": "verifier"}]))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.FAILED and obj.error is not None and obj.error["code"] == "invalid_plan"
    assert "fixed role" in obj.error["message"]
    assert not await oe.tasks(obj.id)
    assert "OBJECTIVE_FAILED" in await oe.event_types(obj.id)


async def test_planning_without_a_usable_model_fails_with_the_reason(app: FastAPI) -> None:
    from app.schemas.orchestration import ObjectiveCreate
    from app.schemas.projects import ProjectCreate

    c = app.state.container
    project = await c.projects.create(ProjectCreate(name="No models"))
    obj = await c.objective_service.create(ObjectiveCreate(project_id=project.id, text="Do something useful"))
    obj = await c.objective_service.wait_for(obj.id)
    assert obj.status is OBJ.FAILED and obj.error["code"] == "planning_failed"
    assert "provider" in obj.error["message"].lower()


async def test_the_plan_can_be_edited_before_it_runs(oe: OE) -> None:
    oe.book.add("Planner", plan(REPORT_TASKS))
    obj = await oe.wait((await oe.create(run_mode="review_plan")).id)
    with pytest.raises(InvalidRequestError, match="unknown agent"):
        await oe.c.objective_service.edit_plan(
            obj.id, PlanEdit(tasks=[PlanTask(key="x", title="x", description="", agent="wizard")])
        )
    detail = await oe.c.objective_service.edit_plan(
        obj.id,
        PlanEdit(tasks=[PlanTask(key="x1", title="Just write it", description="One page", agent="writer")]),
    )
    assert (
        [t.key for t in detail.tasks] == ["x1"]
        and detail.objective.plan is not None
        and detail.objective.plan["edited"]
    )
    assert "PLAN_EDITED" in await oe.event_types(obj.id)
    oe.book.add("Writer", finish("Written"))
    oe.book.add("Verifier", verdict("PASS"))
    await oe.c.objective_service.run(obj.id, ObjectiveRun())
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED
    assert "Just write it" in oe.requests_for("Writer")[0]
    with pytest.raises(ConflictError):
        await oe.c.objective_service.edit_plan(
            obj.id, PlanEdit(tasks=[PlanTask(key="y", title="y", description="", agent="writer")])
        )


# ------------------------------------------------------------------ failure and recovery


async def test_a_failing_task_pauses_the_objective_and_a_retry_finishes_it(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add("Writer", finish("No source data", status="failed", errors=["files/data.csv is missing"]))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.PAUSED
    t1 = (await oe.tasks(obj.id))["t1"]
    assert (
        t1.status is TS.BLOCKED
        and t1.error is not None
        and t1.error["needs_person"]
        and t1.error["decision"] == "block"
    )
    decisions = await oe.events(obj.id, "RECOVERY_DECISION")
    assert decisions[0].payload["action"] == "block"
    assert any("needs you" in n.title for n in await oe.c.notifications.list_all())

    oe.book.add("Writer", finish("Written after the data arrived"))
    oe.book.add("Verifier", verdict("PASS"))
    await oe.c.objective_service.retry_task(t1.id)
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED
    assert (await oe.tasks(obj.id))["t1"].status is TS.COMPLETED


async def test_a_task_stopped_by_its_step_limit_continues_from_its_checkpoint(oe: OE) -> None:
    await oe.c.agent_store.update("writer", AgentUpdate(max_steps=2))
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add(
        "Writer",
        call("calculator", {"expression": "1+1"}),
        call("calculator", {"expression": "2+2"}),
        finish("Finished in the second attempt"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.COMPLETED, obj.error
    t1 = (await oe.tasks(obj.id))["t1"]
    assert t1.attempts == 2 and t1.run_id is not None
    run = await oe.c.run_store.get(t1.run_id)
    assert run.attempt == 2 and run.step_count == 3  # the same run, continued, not restarted from scratch
    actions = [e.payload["action"] for e in await oe.events(obj.id, "RECOVERY_DECISION")]
    assert actions == ["resume"]


async def test_an_optional_task_that_fails_is_skipped_and_the_rest_continue(oe: OE) -> None:
    oe.book.add(
        "Planner",
        plan(
            [
                {"key": "t1", "title": "Nice-to-have research", "agent": "researcher", "optional": True},
                {"key": "t2", "title": "Write", "agent": "writer", "depends_on": ["t1"]},
            ]
        ),
    )
    oe.book.add("Researcher", finish("Could not reach the sources", status="failed"))
    oe.book.add("Writer", finish("Written without research"))
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.COMPLETED
    tasks = await oe.tasks(obj.id)
    assert tasks["t1"].status is TS.SKIPPED and tasks["t2"].status is TS.COMPLETED
    assert "was skipped" in oe.requests_for("Writer")[0]


async def test_a_person_can_skip_a_blocked_task_and_dependents_continue(oe: OE) -> None:
    oe.book.add(
        "Planner",
        plan(
            [
                {"key": "t1", "title": "Research", "agent": "researcher"},
                {"key": "t2", "title": "Write", "agent": "writer", "depends_on": ["t1"]},
            ]
        ),
    )
    oe.book.add("Researcher", finish("Blocked by a paywall", status="failed"))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.PAUSED
    tasks = await oe.tasks(obj.id)
    assert tasks["t1"].status is TS.BLOCKED and tasks["t2"].status is TS.WAITING
    oe.book.add("Writer", finish("Written from what we have"))
    oe.book.add(
        "Verifier",
        verdict("PARTIAL", [("The deliverable exists", True), ("Research included", False)], ["Research"]),
    )
    oe.book.add("Planner", plan([{"key": "f1", "title": "Try research again", "agent": "researcher"}]))
    oe.book.add("Researcher", finish("Found an open source"))
    oe.book.add("Verifier", verdict("PASS", [("The deliverable exists", True)]))
    await oe.c.objective_service.skip_task(tasks["t1"].id)
    obj = await oe.wait(obj.id)
    assert obj.status is OBJ.COMPLETED
    assert (await oe.tasks(obj.id))["t1"].status is TS.SKIPPED


async def test_a_question_pauses_the_objective_and_the_answer_resumes_it(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add(
        "Writer",
        {
            "summary": "Need the tone",
            "action": {"type": "ask_human", "question": "Which tone?", "options": ["formal", "casual"]},
        },
        finish("Written formally"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.PAUSED
    t1 = (await oe.tasks(obj.id))["t1"]
    assert t1.status is TS.BLOCKED and t1.error is not None and t1.error["code"] == "needs_input"
    assert t1.error["message"] == "Which tone?" and t1.error["options"] == ["formal", "casual"]
    detail = await oe.c.objective_service.detail(obj.id)
    assert any(m.type == "QUESTION" and m.recipient == "user" for m in detail.messages)
    await oe.c.objective_service.answer_task(t1.id, "formal")
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED
    assert "The person answered:\nformal" in oe.requests_for("Writer")[-1]


async def test_a_task_waiting_on_approval_shows_it_and_continues_when_approved(oe: OE) -> None:
    await write(oe, "files/old.txt", "old")
    oe.book.add(
        "Planner", plan([{"key": "t1", "title": "Tidy", "agent": "file_manager", "tools": ["delete_file"]}])
    )
    oe.book.add(
        "File Manager",
        call("delete_file", {"path": "files/old.txt"}, "Removing the old file"),
        finish("Removed it"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.create()
    approval = await oe.pending()
    assert await oe.task_status(obj.id, "t1", "NEEDS_APPROVAL") == "NEEDS_APPROVAL"
    assert (await oe.c.objective_service.get(obj.id)).status is OBJ.RUNNING
    assert (await oe.tasks(obj.id))["t1"].approval_required  # the plan said so up front
    await oe.decide(approval, "approve_once")
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED


async def test_verification_gaps_get_one_round_of_follow_up_work(oe: OE) -> None:
    oe.book.add(
        "Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}], ["Has a pricing table"])
    )
    oe.book.add("Writer", finish("Wrote the text"))
    oe.book.add("Verifier", verdict("PARTIAL", [("Has a pricing table", False)], ["Add a pricing table"]))
    oe.book.add(
        "Planner",
        plan([{"key": "f1", "title": "Add the pricing table", "agent": "writer", "depends_on": ["t1"]}]),
    )
    oe.book.add("Writer", finish("Added the table"))
    oe.book.add("Verifier", verdict("PASS", [("Has a pricing table", True)]))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.COMPLETED and obj.replan_count == 1
    assert list(await oe.tasks(obj.id)) == ["t1", "verify1", "f1", "verify2"]
    follow_up_prompt = oe.requests_for("Planner")[1]
    assert "Add a pricing table" in follow_up_prompt and "t1" in follow_up_prompt
    assert obj.plan is not None and len(obj.plan["follow_up"]) == 1
    assert "PLAN_EDITED" in await oe.event_types(obj.id)


async def test_an_objective_that_still_fails_verification_ends_failed_with_what_is_missing(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}], ["Cites sources"]))
    oe.book.add("Writer", finish("Wrote it"))
    oe.book.add("Verifier", verdict("FAIL", [("Cites sources", False)], ["Sources"]))
    oe.book.add("Planner", plan([{"key": "f1", "title": "Add sources", "agent": "writer"}]))
    oe.book.add("Writer", finish("Tried to add sources"))
    oe.book.add("Verifier", verdict("FAIL", [("Cites sources", False)], ["Sources are still missing"]))
    obj = await oe.wait((await oe.create()).id)
    assert obj.status is OBJ.FAILED and obj.replan_count == 1
    assert obj.result is not None and obj.result["verdict"] == "FAIL"
    assert obj.result["missing_requirements"] == ["Sources are still missing"]
    assert "OBJECTIVE_FAILED" in await oe.event_types(obj.id)


# ------------------------------------------------------------------ control


async def test_cancelling_a_running_objective_stops_its_agents_and_approvals(oe: OE) -> None:
    await write(oe, "files/old.txt", "old")
    oe.book.add("Planner", plan([{"key": "t1", "title": "Tidy", "agent": "file_manager"}]))
    oe.book.add("File Manager", call("delete_file", {"path": "files/old.txt"}), finish("done"))
    obj = await oe.create()
    approval = await oe.pending()
    cancelled = await oe.c.objective_service.cancel(obj.id)
    assert cancelled.status is OBJ.CANCELLED and cancelled.completed_at is not None
    t1 = (await oe.tasks(obj.id))["t1"]
    assert t1.status is TS.CANCELLED
    assert (await oe.c.approvals.get(approval.id)).status == "CANCELLED"
    assert t1.run_id and (await oe.c.run_store.get(t1.run_id)).status is RunStatus.CANCELLED
    assert (await oe.c.projects.project_dir(oe.project_id) / "files/old.txt").exists()
    assert "OBJECTIVE_CANCELLED" in await oe.event_types(obj.id)
    assert (await oe.c.objective_service.cancel(obj.id)).status is OBJ.CANCELLED  # idempotent


async def test_after_a_restart_an_objective_resumes_where_it_stopped(oe: OE) -> None:
    await write(oe, "files/old.txt", "old")
    oe.book.add("Planner", plan([{"key": "t1", "title": "Tidy", "agent": "file_manager"}]))
    oe.book.add(
        "File Manager",
        call("delete_file", {"path": "files/old.txt"}),
        call("delete_file", {"path": "files/old.txt"}, "Checking and deleting again"),
        finish("Removed it"),
    )
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.create()
    await oe.pending()

    # the app stops while the task waits on an approval
    await oe.c.objective_service.shutdown()
    oe.c.orchestrator.shutting_down = oe.c.runner.shutting_down = False
    assert (await oe.c.objective_service.get(obj.id)).status is OBJ.PAUSED
    t1 = (await oe.tasks(obj.id))["t1"]
    assert t1.run_id and (await oe.c.run_store.get(t1.run_id)).status is RunStatus.INTERRUPTED

    # startup recovery, then the person presses Resume
    await oe.c.agent_service.recover()
    await oe.c.objective_service.recover()
    t1 = (await oe.tasks(obj.id))["t1"]
    assert t1.status is TS.QUEUED and t1.resume
    await oe.c.objective_service.resume(obj.id)
    approval = await oe.pending()
    await oe.decide(approval, "approve_once")
    obj = await oe.wait(obj.id)
    assert obj.status is OBJ.COMPLETED
    assert "interrupted by an application restart" in oe.requests_for("File Manager")[-2]
    assert not (await oe.c.projects.project_dir(oe.project_id) / "files/old.txt").exists()


async def test_an_objective_interrupted_while_planning_is_replanned_on_resume(oe: OE) -> None:
    obj = await oe.c.objective_store.create(
        project_id=oe.project_id,
        text="Plan me",
        run_mode="auto",
        execution_mode="normal",
        attachments=[],
        budget={},
        replan_count=0,
        private=False,
    )
    await oe.c.objective_store.update(obj.id, status=OBJ.PLANNING)
    [back] = await oe.c.objective_service.recover()
    assert back.status is OBJ.RECEIVED
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add("Writer", finish("ok"))
    oe.book.add("Verifier", verdict("PASS"))
    await oe.c.objective_service.resume(obj.id)
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED


async def test_safe_only_mode_asks_before_anything_that_is_not_safe(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    oe.book.add("Writer", call("create_markdown", {"name": "a.md", "content": "x"}), finish("ok"))
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create(run_mode="review_plan")).id)
    await oe.c.objective_service.run(obj.id, ObjectiveRun(mode="safe_only"))
    approval = await oe.pending()
    assert approval.tool_name == "create_markdown" and approval.risk_level.value == "MODERATE"
    await oe.decide(approval, "approve_once")
    assert (await oe.wait(obj.id)).status is OBJ.COMPLETED


async def test_a_private_objective_keeps_every_run_private(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Research", "agent": "researcher"}]))
    oe.book.add("Researcher", finish("Used local files only"))
    oe.book.add("Verifier", verdict("PASS"))
    obj = await oe.wait((await oe.create(private=True)).id)
    assert obj.status is OBJ.COMPLETED
    runs = await oe.c.run_store.list_runs(project_id=oe.project_id)
    assert len(runs) == 3
    for r in runs:
        request, _ = await oe.c.run_store.snapshot(r.id)
        assert request["private"] is True
    researcher = oe.requests_for("Researcher")[0].split("## Your tools")[1]
    assert "web_search" not in researcher and "http_request" not in researcher


async def test_objectives_on_archived_projects_are_refused(oe: OE) -> None:
    await oe.c.projects.set_status(oe.project_id, "archived")
    with pytest.raises(ConflictError, match="archived"):
        await oe.create()


async def test_retry_skip_and_answer_refuse_the_wrong_state(oe: OE) -> None:
    oe.book.add("Planner", plan([{"key": "t1", "title": "Write", "agent": "writer"}]))
    obj = await oe.wait((await oe.create(run_mode="review_plan")).id)
    t1 = (await oe.tasks(obj.id))["t1"]
    for action in (oe.c.objective_service.retry_task, oe.c.objective_service.skip_task):
        with pytest.raises(ConflictError):
            await action(t1.id)
    with pytest.raises(ConflictError, match="not waiting for an answer"):
        await oe.c.objective_service.answer_task(t1.id, "hello")
    with pytest.raises(ConflictError, match="paused"):
        await oe.c.objective_service.resume(obj.id)
