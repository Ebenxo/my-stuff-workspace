"""The timeline: one view of what is happening now, what needs the person, what is coming up, and what
they pinned. History ("earlier") is the event log itself, paged through ``/api/events``.

Everything here is read from the stores of record; nothing is cached or guessed.
"""

from __future__ import annotations

from datetime import datetime

from app.core.clock import Clock, SystemClock
from app.repositories.idea_store import IdeaStore
from app.repositories.orchestration_store import ObjectiveStore
from app.repositories.runtime_store import AgentStore, ApprovalStore, RunStore
from app.repositories.workflow_store import ScheduleStore, WorkflowRunStore, WorkflowStore
from app.scheduler import cron
from app.schemas.ideas import IdeaOut, TimelineItem, TimelineOut
from app.schemas.orchestration import ObjectiveOut, ObjectiveStatus
from app.schemas.runtime import ApprovalStatus, RunStatus
from app.schemas.workflows import WorkflowRunStatus
from app.services.ideas import KIND_LABEL, title_of

LIST_LIMIT = 50

_OBJECTIVE_ACTIVE = (
    ObjectiveStatus.RECEIVED,
    ObjectiveStatus.PLANNING,
    ObjectiveStatus.RUNNING,
    ObjectiveStatus.VERIFYING,
)
_OBJECTIVE_WAITING = (ObjectiveStatus.AWAITING_PLAN_APPROVAL, ObjectiveStatus.PAUSED)
_WAITING_DETAIL = {
    ObjectiveStatus.AWAITING_PLAN_APPROVAL: "The plan is ready for your review.",
    ObjectiveStatus.PAUSED: "Paused until you answer or decide what to do.",
}


def _by_time(items: list[TimelineItem], *, newest_first: bool = False) -> list[TimelineItem]:
    """Dated items in time order (soonest first, or newest first), then any undated ones."""
    dated = sorted(
        (i for i in items if i.at is not None),
        key=lambda i: i.at.timestamp() if i.at else 0.0,
        reverse=newest_first,
    )
    return dated + [i for i in items if i.at is None]


class TimelineService:
    def __init__(
        self,
        *,
        objectives: ObjectiveStore,
        runs: RunStore,
        agents: AgentStore,
        approvals: ApprovalStore,
        workflows: WorkflowStore,
        workflow_runs: WorkflowRunStore,
        schedules: ScheduleStore,
        ideas: IdeaStore,
        clock: Clock | None = None,
    ) -> None:
        self._objectives = objectives
        self._runs = runs
        self._agents = agents
        self._approvals = approvals
        self._workflows = workflows
        self._workflow_runs = workflow_runs
        self._schedules = schedules
        self._ideas = ideas
        self._clock = clock or SystemClock()

    async def build(self, *, project_id: str | None = None) -> TimelineOut:
        now = self._clock.now()
        agent_names = {a.id: a.name for a in await self._agents.list_all()}
        workflows = {w.id: w for w in await self._workflows.list_workflows()}

        def in_scope(pid: str | None) -> bool:
            return project_id is None or pid == project_id

        objectives = [
            o
            for o in await self._objectives.in_states([*_OBJECTIVE_ACTIVE, *_OBJECTIVE_WAITING])
            if in_scope(o.project_id)
        ]
        objective_titles = {o.id: title_of(o.text) for o in objectives}

        now_items: list[TimelineItem] = []
        waiting: list[TimelineItem] = []
        upcoming: list[TimelineItem] = []
        pinned: list[TimelineItem] = []

        # ---- objectives
        for o in objectives:
            item = self._objective_item(o)
            (waiting if o.status in _OBJECTIVE_WAITING else now_items).append(item)

        # ---- agent runs (approvals cover the ones waiting on an approval)
        for status in (RunStatus.RUNNING, RunStatus.WAITING_INPUT):
            for r in await self._runs.list_runs(project_id=project_id, status=status.value, limit=LIST_LIMIT):
                name = agent_names.get(r.agent_id, "An agent")
                asks = status is RunStatus.WAITING_INPUT
                part_of = objective_titles.get(r.objective_id or "")
                first_line = (r.prompt.strip().splitlines() or [""])[0][:160]
                item = TimelineItem(
                    kind="agent_run",
                    id=r.id,
                    title=f"{name} has a question" if asks else f"{name} is working",
                    detail=f"Part of “{part_of}”" if part_of else first_line,
                    status=r.status.value,
                    project_id=r.project_id,
                    at=r.started_at,
                    ref_id=r.objective_id,
                )
                (waiting if asks else now_items).append(item)

        # ---- workflow runs
        for run in await self._workflow_runs.list_runs(
            project_id=project_id,
            statuses=(WorkflowRunStatus.RUNNING.value, WorkflowRunStatus.WAITING.value),
            limit=LIST_LIMIT,
        ):
            wf = workflows.get(run.workflow_id)
            name = wf.name if wf else "A workflow"
            is_waiting = run.status is WorkflowRunStatus.WAITING
            item = TimelineItem(
                kind="workflow_run",
                id=run.id,
                title=f"{name} is waiting for you" if is_waiting else f"{name} is running",
                detail=("Started by its schedule" if run.schedule_id else "Started by you")
                + (" (unattended)" if run.unattended else ""),
                status=run.status.value,
                project_id=run.project_id,
                at=run.started_at,
                ref_id=run.workflow_id,
            )
            (waiting if is_waiting else now_items).append(item)

        # ---- approvals
        for a in await self._approvals.list_approvals(
            status=ApprovalStatus.PENDING.value, project_id=project_id, limit=LIST_LIMIT
        ):
            waiting.append(
                TimelineItem(
                    kind="approval",
                    id=a.id,
                    title=f"Approve “{a.tool_name}”?",
                    detail=a.reason or a.impact,
                    status=a.status.value,
                    project_id=a.project_id,
                    at=a.created_at,
                    ref_id=a.run_id,
                )
            )

        # ---- schedules
        for s in await self._schedules.list_schedules():
            wf = workflows.get(s.workflow_id)
            if not s.enabled or s.next_run_at is None or wf is None or not in_scope(wf.project_id):
                continue
            try:
                description = cron.describe(cron.parse(s.cron))
            except cron.CronError:
                description = s.cron
            upcoming.append(
                TimelineItem(
                    kind="schedule",
                    id=s.id,
                    title=f"{wf.name} runs",
                    detail=description + ("" if wf.enabled else " (the workflow is turned off)"),
                    status="SCHEDULED",
                    project_id=wf.project_id,
                    at=s.next_run_at,
                    ref_id=wf.id,
                )
            )

        # ---- ideas, notes and to-dos
        for idea in await self._ideas.list_ideas(status="open", project_id=project_id, limit=500):
            if idea.due_at is not None:
                (waiting if idea.due_at <= now else upcoming).append(self._idea_item(idea, now))
            elif idea.pinned:
                pinned.append(self._idea_item(idea, now))

        return TimelineOut(
            generated_at=now,
            now=_by_time(now_items, newest_first=True)[:LIST_LIMIT],
            waiting=_by_time(waiting)[:LIST_LIMIT],
            next=_by_time(upcoming)[:LIST_LIMIT],
            pinned=pinned[:LIST_LIMIT],
        )

    @staticmethod
    def _objective_item(o: ObjectiveOut) -> TimelineItem:
        waiting_detail = _WAITING_DETAIL.get(o.status)
        return TimelineItem(
            kind="objective",
            id=o.id,
            title=title_of(o.text),
            detail=waiting_detail or ("Private: stays on this device" if o.private else ""),
            status=o.status.value,
            project_id=o.project_id,
            at=o.updated_at if waiting_detail else o.created_at,
        )

    @staticmethod
    def _idea_item(idea: IdeaOut, now: datetime) -> TimelineItem:
        overdue = idea.due_at is not None and idea.due_at <= now
        return TimelineItem(
            kind="idea",
            id=idea.id,
            title=title_of(idea.text),
            detail=KIND_LABEL.get(idea.kind, "Item") + (" · pinned" if idea.pinned else ""),
            status="OVERDUE" if overdue else ("DUE" if idea.due_at else "OPEN"),
            project_id=idea.project_id,
            at=idea.due_at or idea.created_at,
            idea_kind=idea.kind,
        )
