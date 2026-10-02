"""Domain stores for the agent runtime. They own their sessions and return DTOs, so higher layers
(agents, orchestration) depend on these interfaces and never on the ORM."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, NotFoundError
from app.core.ids import new_id
from app.core.risk import RiskLevel
from app.core.slug import slugify_agent
from app.models.database import Database
from app.models.runtime import Agent, AgentRun, Approval, Artifact, ArtifactVersion, Tool, ToolCall
from app.schemas.agents import AgentCreate, AgentDefinition, AgentUpdate
from app.schemas.runtime import (
    AgentRunOut,
    ApprovalOut,
    ApprovalStatus,
    ArtifactOut,
    ArtifactVersionOut,
    RunStatus,
    ToolCallOut,
    ToolCallStatus,
    ToolOut,
)

# Fields a user may override on a built-in agent. Everything else comes from code.
BUILTIN_OVERRIDABLE = frozenset(
    {
        "preferred_model",
        "fallback_models",
        "temperature",
        "max_steps",
        "max_runtime_s",
        "max_tool_calls",
        "token_budget",
        "tools",
        "reasoning_mode",
        "status",
        "permissions",
    }
)


def _definition(row: Agent) -> AgentDefinition:
    data: dict[str, Any] = {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "role": row.role,
        "description": row.description,
        "icon": row.icon,
        "color": row.color,
        "system_prompt": row.system_prompt,
        "preferred_model": row.preferred_model,
        "fallback_models": row.fallback_models,
        "tools": row.tools,
        "permissions": row.permissions or {},
        "memory_scope": row.memory_scope or {},
        "max_steps": row.max_steps,
        "max_runtime_s": row.max_runtime_s,
        "max_tool_calls": row.max_tool_calls,
        "token_budget": row.token_budget,
        "temperature": row.temperature,
        "reasoning_mode": row.reasoning_mode,
        "status": row.status,
        "builtin": row.builtin,
        "knowledge_sources": row.knowledge_sources,
        "version": row.version,
    }
    if row.builtin:
        data.update({k: v for k, v in (row.overrides or {}).items() if k in BUILTIN_OVERRIDABLE})
    return AgentDefinition.model_validate(data)


class AgentStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def upsert_builtin(self, d: AgentDefinition) -> AgentDefinition:
        """Insert or refresh a built-in from code. User overrides are preserved."""
        async with self._db.session() as s:
            row = (await s.execute(select(Agent).where(Agent.slug == d.slug))).scalar_one_or_none()
            now = self._clock.now()
            values = d.model_dump(mode="json", exclude={"id"})
            if row is None:
                row = Agent(id=d.id, created_at=now, updated_at=now, overrides={}, **values)
                s.add(row)
            else:
                for k, v in values.items():
                    setattr(row, k, v)
                row.builtin = True
                row.updated_at = now
            await s.flush()
            return _definition(row)

    async def list_all(self) -> list[AgentDefinition]:
        async with self._db.session() as s:
            rows = (
                (await s.execute(select(Agent).order_by(Agent.builtin.desc(), Agent.created_at.asc())))
                .scalars()
                .all()
            )
            return [_definition(r) for r in rows]

    async def get(self, id_or_slug: str) -> AgentDefinition:
        async with self._db.session() as s:
            row = (
                await s.execute(select(Agent).where((Agent.id == id_or_slug) | (Agent.slug == id_or_slug)))
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError(f"Agent {id_or_slug} not found")
            return _definition(row)

    async def create(self, data: AgentCreate) -> AgentDefinition:
        async with self._db.session() as s:
            base = slugify_agent(data.name)
            slug, n = base, 1
            while (await s.execute(select(Agent.id).where(Agent.slug == slug))).first():
                n += 1
                slug = f"{base}-{n}"
            now = self._clock.now()
            row = Agent(
                id=new_id("agent"),
                slug=slug,
                builtin=False,
                status="idle",
                overrides={},
                created_at=now,
                updated_at=now,
                **data.model_dump(mode="json"),
            )
            s.add(row)
            await s.flush()
            return _definition(row)

    async def update(self, id_or_slug: str, patch: AgentUpdate) -> AgentDefinition:
        changes = patch.model_dump(mode="json", exclude_unset=True)
        async with self._db.session() as s:
            row = (
                await s.execute(select(Agent).where((Agent.id == id_or_slug) | (Agent.slug == id_or_slug)))
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError(f"Agent {id_or_slug} not found")
            if row.builtin:
                allowed = {k: v for k, v in changes.items() if k in BUILTIN_OVERRIDABLE}
                rejected = sorted(set(changes) - set(allowed))
                if rejected:
                    permitted = ", ".join(sorted(BUILTIN_OVERRIDABLE))
                    raise ConflictError(
                        f"Built-in agents only allow changing: {permitted}. "
                        f"Not allowed: {', '.join(rejected)}."
                    )
                row.overrides = {**(row.overrides or {}), **allowed}
            else:
                for k, v in changes.items():
                    setattr(row, k, v)
            row.version += 1
            row.updated_at = self._clock.now()
            await s.flush()
            return _definition(row)

    async def delete(self, id_or_slug: str) -> None:
        async with self._db.session() as s:
            row = (
                await s.execute(select(Agent).where((Agent.id == id_or_slug) | (Agent.slug == id_or_slug)))
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError(f"Agent {id_or_slug} not found")
            if row.builtin:
                raise ConflictError("Built-in agents cannot be deleted. Disable them instead.")
            await s.delete(row)

    async def set_status(self, agent_id: str, status: str) -> None:
        async with self._db.session() as s:
            await s.execute(update(Agent).where(Agent.id == agent_id).values(status=status))


class RunStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(
        self,
        *,
        run_id: str,
        agent_id: str,
        project_id: str | None,
        objective_id: str | None,
        task_id: str | None,
        model: str | None,
        request: dict[str, Any],
        attempt: int = 1,
        context_report: dict[str, Any] | None = None,
    ) -> AgentRunOut:
        async with self._db.session() as s:
            row = AgentRun(
                id=run_id,
                agent_id=agent_id,
                project_id=project_id,
                objective_id=objective_id,
                task_id=task_id,
                status=RunStatus.RUNNING.value,
                model=model,
                request=request,
                attempt=attempt,
                checkpoint=[],
                context_report=context_report,
                started_at=self._clock.now(),
            )
            s.add(row)
            await s.flush()
            return AgentRunOut.model_validate(row)

    async def get(self, run_id: str) -> AgentRunOut:
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            return AgentRunOut.model_validate(row)

    async def snapshot(self, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """(original request, checkpoint steps): everything needed to resume."""
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            return dict(row.request), list(row.checkpoint)

    async def context_report(self, run_id: str) -> dict[str, Any] | None:
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            return dict(row.context_report) if row.context_report else None

    async def save_progress(
        self,
        run_id: str,
        *,
        checkpoint: list[dict[str, Any]],
        step_count: int,
        tool_call_count: int,
        tokens_in: int,
        tokens_out: int,
        model: str | None,
    ) -> None:
        async with self._db.session() as s:
            await s.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    checkpoint=checkpoint,
                    step_count=step_count,
                    tool_call_count=tool_call_count,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    model=model,
                )
            )

    async def set_status(
        self, run_id: str, status: RunStatus, *, result: dict[str, Any] | None = None
    ) -> None:
        """Change status. ``result`` is only written when given (e.g. the question of a run that waits)."""
        values: dict[str, Any] = {"status": status.value}
        if result is not None:
            values["result"] = result
        async with self._db.session() as s:
            await s.execute(update(AgentRun).where(AgentRun.id == run_id).values(**values))

    async def reopen(self, run_id: str) -> AgentRunOut:
        """A run that was waiting for a person continues (same attempt)."""
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            row.status, row.result = RunStatus.RUNNING.value, None
            await s.flush()
            return AgentRunOut.model_validate(row)

    async def finish(
        self,
        run_id: str,
        status: RunStatus,
        *,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> AgentRunOut:
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            row.status, row.result, row.error, row.finished_at = (
                status.value,
                result,
                error,
                self._clock.now(),
            )
            await s.flush()
            return AgentRunOut.model_validate(row)

    async def restart(self, run_id: str) -> AgentRunOut:
        """Reopen an interrupted/failed run for resumption; the attempt counter increases."""
        async with self._db.session() as s:
            row = await s.get(AgentRun, run_id)
            if row is None:
                raise NotFoundError(f"Run {run_id} not found")
            row.status, row.finished_at, row.error, row.result, row.attempt = (
                RunStatus.RUNNING.value,
                None,
                None,
                None,
                row.attempt + 1,
            )
            await s.flush()
            return AgentRunOut.model_validate(row)

    async def list_runs(
        self,
        *,
        project_id: str | None = None,
        agent_id: str | None = None,
        status: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentRunOut]:
        stmt = select(AgentRun).order_by(AgentRun.id.desc()).limit(limit)
        if project_id:
            stmt = stmt.where(AgentRun.project_id == project_id)
        if agent_id:
            stmt = stmt.where(AgentRun.agent_id == agent_id)
        if status:
            stmt = stmt.where(AgentRun.status == status)
        if task_id:
            stmt = stmt.where(AgentRun.task_id == task_id)
        async with self._db.session() as s:
            return [AgentRunOut.model_validate(r) for r in (await s.execute(stmt)).scalars().all()]

    async def mark_interrupted(self) -> list[AgentRunOut]:
        """At startup: anything still RUNNING/WAITING was cut off by a restart. Keep the checkpoint."""
        open_states = [
            RunStatus.RUNNING.value,
            RunStatus.WAITING_APPROVAL.value,
            RunStatus.WAITING_INPUT.value,
        ]
        async with self._db.session() as s:
            rows = (await s.execute(select(AgentRun).where(AgentRun.status.in_(open_states)))).scalars().all()
            for r in rows:
                r.status = RunStatus.INTERRUPTED.value
            await s.flush()
            return [AgentRunOut.model_validate(r) for r in rows]


class ToolCallStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(
        self,
        *,
        run_id: str | None,
        task_id: str | None,
        project_id: str | None,
        tool_name: str,
        summary: str,
        arguments: dict[str, Any],
        risk: RiskLevel,
        status: ToolCallStatus,
    ) -> ToolCallOut:
        async with self._db.session() as s:
            row = ToolCall(
                id=new_id("tc"),
                run_id=run_id,
                task_id=task_id,
                project_id=project_id,
                tool_name=tool_name,
                summary=summary[:500],
                arguments=arguments,
                status=status.value,
                risk_level=risk.value,
                started_at=self._clock.now(),
            )
            s.add(row)
            await s.flush()
            return ToolCallOut.model_validate(row)

    async def update(self, call_id: str, **fields: Any) -> ToolCallOut:
        async with self._db.session() as s:
            row = await s.get(ToolCall, call_id)
            if row is None:
                raise NotFoundError(f"Tool call {call_id} not found")
            for k, v in fields.items():
                setattr(row, k, v.value if hasattr(v, "value") else v)
            await s.flush()
            return ToolCallOut.model_validate(row)

    async def get(self, call_id: str) -> ToolCallOut:
        async with self._db.session() as s:
            row = await s.get(ToolCall, call_id)
            if row is None:
                raise NotFoundError(f"Tool call {call_id} not found")
            return ToolCallOut.model_validate(row)

    async def close_open(self, run_ids: Sequence[str], code: str, message: str) -> int:
        """Tool calls still in flight for runs that no longer exist as processes (e.g. after a restart)."""
        if not run_ids:
            return 0
        open_states = [
            ToolCallStatus.PROPOSED.value,
            ToolCallStatus.AWAITING_APPROVAL.value,
            ToolCallStatus.RUNNING.value,
        ]
        async with self._db.session() as s:
            result = await s.execute(
                update(ToolCall)
                .where(ToolCall.run_id.in_(list(run_ids)), ToolCall.status.in_(open_states))
                .values(
                    status=ToolCallStatus.FAILED.value,
                    error={"code": code, "message": message},
                    finished_at=self._clock.now(),
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def list_calls(
        self,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ToolCallOut]:
        stmt = select(ToolCall).order_by(ToolCall.id.desc()).limit(limit)
        for col, val in (
            (ToolCall.project_id, project_id),
            (ToolCall.run_id, run_id),
            (ToolCall.task_id, task_id),
            (ToolCall.status, status),
        ):
            if val:
                stmt = stmt.where(col == val)
        async with self._db.session() as s:
            return [ToolCallOut.model_validate(r) for r in (await s.execute(stmt)).scalars().all()]


class ApprovalStore:
    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def create(self, **fields: Any) -> ApprovalOut:
        async with self._db.session() as s:
            row = Approval(
                id=new_id("appr"), status=ApprovalStatus.PENDING.value, created_at=self._clock.now(), **fields
            )
            s.add(row)
            await s.flush()
            return ApprovalOut.model_validate(row)

    async def get(self, approval_id: str) -> ApprovalOut:
        async with self._db.session() as s:
            row = await s.get(Approval, approval_id)
            if row is None:
                raise NotFoundError(f"Approval {approval_id} not found")
            return ApprovalOut.model_validate(row)

    async def list_approvals(
        self,
        *,
        status: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> list[ApprovalOut]:
        stmt = select(Approval).order_by(Approval.id.desc()).limit(limit)
        for col, val in (
            (Approval.status, status),
            (Approval.project_id, project_id),
            (Approval.run_id, run_id),
        ):
            if val:
                stmt = stmt.where(col == val)
        async with self._db.session() as s:
            return [ApprovalOut.model_validate(r) for r in (await s.execute(stmt)).scalars().all()]

    async def decide(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        decided_by: str,
        note: str | None = None,
        edited_arguments: dict[str, Any] | None = None,
    ) -> ApprovalOut:
        """Atomically move PENDING -> ``status``. A second decision on the same approval is a conflict."""
        async with self._db.session() as s:
            result = await s.execute(
                update(Approval)
                .where(Approval.id == approval_id, Approval.status == ApprovalStatus.PENDING.value)
                .values(
                    status=status.value,
                    decided_by=decided_by,
                    decision_note=note,
                    edited_arguments=edited_arguments,
                    decided_at=self._clock.now(),
                )
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                row = await s.get(Approval, approval_id)
                if row is None:
                    raise NotFoundError(f"Approval {approval_id} not found")
                raise ConflictError(f"This approval was already {row.status.lower().replace('_', ' ')}.")
            row = await s.get(Approval, approval_id)
            assert row is not None
            await s.refresh(row)
            return ApprovalOut.model_validate(row)

    async def link_tool_call(self, approval_id: str, tool_call_id: str) -> None:
        async with self._db.session() as s:
            await s.execute(
                update(Approval).where(Approval.id == approval_id).values(tool_call_id=tool_call_id)
            )

    async def cancel_open_for_runs(self, run_ids: Sequence[str], note: str) -> int:
        if not run_ids:
            return 0
        async with self._db.session() as s:
            result = await s.execute(
                update(Approval)
                .where(Approval.run_id.in_(list(run_ids)), Approval.status == ApprovalStatus.PENDING.value)
                .values(
                    status=ApprovalStatus.CANCELLED.value,
                    decision_note=note,
                    decided_at=self._clock.now(),
                    decided_by="system",
                )
            )
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def expire_before(self, cutoff: datetime) -> list[str]:
        async with self._db.session() as s:
            ids = list(
                (
                    await s.execute(
                        select(Approval.id).where(
                            Approval.status == ApprovalStatus.PENDING.value, Approval.created_at < cutoff
                        )
                    )
                ).scalars()
            )
            if ids:
                await s.execute(
                    update(Approval)
                    .where(Approval.id.in_(ids))
                    .values(
                        status=ApprovalStatus.EXPIRED.value,
                        decided_by="system",
                        decided_at=self._clock.now(),
                        decision_note="Expired without a decision",
                    )
                )
            return ids


class ToolRowStore:
    """Mirror of the in-memory registry so the UI can list tools and users can disable them."""

    def __init__(self, db: Database, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def sync(self, rows: Sequence[dict[str, Any]]) -> None:
        async with self._db.session() as s:
            existing = {t.name: t for t in (await s.execute(select(Tool))).scalars().all()}
            names = {r["name"] for r in rows}
            for r in rows:
                cur = existing.get(r["name"])
                if cur is None:
                    s.add(Tool(updated_at=self._clock.now(), enabled=True, **r))
                else:
                    for k, v in r.items():
                        setattr(cur, k, v)  # keeps the user's `enabled` choice
                    cur.updated_at = self._clock.now()
            for name, cur in existing.items():
                if name not in names and cur.source == "builtin":
                    await s.delete(cur)

    async def sync_source(self, source: str, rows: Sequence[dict[str, Any]]) -> list[tuple[str, str]]:
        """Mirror one source's tools (an MCP server's). Each row carries a ``fingerprint`` of its definition
        and, optionally, a ``flag`` (why it looks unsafe). A new tool starts on unless flagged; a tool whose
        definition changed since it was last seen is switched off until the person turns it on again.
        Tools the source no longer offers are removed. Returns (name, reason) for each tool switched off."""
        switched_off: list[tuple[str, str]] = []
        async with self._db.session() as s:
            existing = {
                t.name: t
                for t in (await s.execute(select(Tool).where(Tool.source == source))).scalars().all()
            }
            names = set()
            for r in rows:
                data = {k: v for k, v in r.items() if k != "flag"}
                flag: str | None = r.get("flag")
                names.add(data["name"])
                cur = existing.get(data["name"])
                if cur is None:
                    s.add(Tool(updated_at=self._clock.now(), enabled=flag is None, note=flag, **data))
                    if flag:
                        switched_off.append((data["name"], flag))
                    continue
                changed = cur.fingerprint is not None and cur.fingerprint != data.get("fingerprint")
                for k, v in data.items():
                    setattr(cur, k, v)
                cur.updated_at = self._clock.now()
                if changed:
                    reason = (
                        flag
                        or "The server changed this tool's description or arguments since you last saw it."
                    )
                    if cur.enabled:
                        switched_off.append((cur.name, reason))
                    cur.enabled, cur.note = False, reason
            for name, cur in existing.items():
                if name not in names:
                    await s.delete(cur)
        return switched_off

    async def delete_source(self, source: str) -> None:
        async with self._db.session() as s:
            for cur in (await s.execute(select(Tool).where(Tool.source == source))).scalars().all():
                await s.delete(cur)

    async def list_tools(self) -> list[ToolOut]:
        async with self._db.session() as s:
            rows = (await s.execute(select(Tool).order_by(Tool.source, Tool.name))).scalars().all()
            return [
                ToolOut(
                    name=r.name,
                    source=r.source,
                    description=r.description,
                    risk_level=RiskLevel(r.risk_level),
                    requires_approval=r.requires_approval,
                    capabilities=list(r.capabilities),
                    enabled=r.enabled,
                    input_schema=r.input_schema,
                    note=r.note,
                )
                for r in rows
            ]

    async def disabled_names(self) -> set[str]:
        async with self._db.session() as s:
            return set((await s.execute(select(Tool.name).where(Tool.enabled.is_(False)))).scalars())

    async def set_enabled(self, name: str, enabled: bool) -> None:
        values: dict[str, Any] = {"enabled": enabled}
        if enabled:
            values["note"] = None  # the person has looked at it
        async with self._db.session() as s:
            result = await s.execute(update(Tool).where(Tool.name == name).values(**values))
            if result.rowcount == 0:  # type: ignore[attr-defined]
                raise NotFoundError(f"Tool {name} not found")


class ArtifactRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, project_id: str, path: str) -> tuple[ArtifactOut, list[ArtifactVersionOut]] | None:
        async with self._db.session() as s:
            row = (
                await s.execute(
                    select(Artifact).where(Artifact.project_id == project_id, Artifact.path == path)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            versions = (
                (
                    await s.execute(
                        select(ArtifactVersion)
                        .where(ArtifactVersion.artifact_id == row.id)
                        .order_by(ArtifactVersion.version)
                    )
                )
                .scalars()
                .all()
            )
            return ArtifactOut.model_validate(row), [ArtifactVersionOut.model_validate(v) for v in versions]

    async def create(self, artifact: dict[str, Any], version: dict[str, Any]) -> ArtifactOut:
        async with self._db.session() as s:
            row = Artifact(**artifact)
            s.add(row)
            await s.flush()
            s.add(ArtifactVersion(id=new_id("artv"), artifact_id=row.id, **version))
            await s.flush()
            return ArtifactOut.model_validate(row)

    async def add_version(
        self,
        artifact_id: str,
        version: dict[str, Any],
        *,
        agent_id: str | None,
        task_id: str | None,
        meta: dict[str, Any],
    ) -> ArtifactOut:
        async with self._db.session() as s:
            row = await s.get(Artifact, artifact_id)
            if row is None:
                raise NotFoundError(f"Artifact {artifact_id} not found")
            row.version = version["version"]
            row.agent_id = agent_id or row.agent_id
            row.task_id = task_id or row.task_id
            row.meta = {**row.meta, **meta}
            s.add(ArtifactVersion(id=new_id("artv"), artifact_id=artifact_id, **version))
            await s.flush()
            return ArtifactOut.model_validate(row)

    async def get(self, artifact_id: str) -> ArtifactOut:
        async with self._db.session() as s:
            row = await s.get(Artifact, artifact_id)
            if row is None:
                raise NotFoundError(f"Artifact {artifact_id} not found")
            return ArtifactOut.model_validate(row)

    async def versions(self, artifact_id: str) -> list[tuple[ArtifactVersionOut, str]]:
        """(version DTO, stored_path) pairs, oldest first."""
        async with self._db.session() as s:
            rows = (
                (
                    await s.execute(
                        select(ArtifactVersion)
                        .where(ArtifactVersion.artifact_id == artifact_id)
                        .order_by(ArtifactVersion.version)
                    )
                )
                .scalars()
                .all()
            )
            return [(ArtifactVersionOut.model_validate(v), v.stored_path) for v in rows]

    async def list_artifacts(
        self, *, project_id: str, objective_id: str | None = None, type_: str | None = None, limit: int = 200
    ) -> list[ArtifactOut]:
        stmt = (
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.updated_at.desc())
            .limit(limit)
        )
        if objective_id:
            stmt = stmt.where(Artifact.objective_id == objective_id)
        if type_:
            stmt = stmt.where(Artifact.type == type_)
        async with self._db.session() as s:
            return [ArtifactOut.model_validate(r) for r in (await s.execute(stmt)).scalars().all()]
