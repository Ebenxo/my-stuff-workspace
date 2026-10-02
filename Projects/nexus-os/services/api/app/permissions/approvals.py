"""Approvals: human decisions on proposed actions. The database row is the source of truth, so a
run parked on an approval survives restarts; in-memory events only make waking fast."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.errors import ConflictError, InvalidRequestError
from app.core.ids import new_id
from app.core.risk import RiskLevel
from app.core.security import redact
from app.events.bus import EventBus
from app.events.types import EventType
from app.repositories.runtime_store import ApprovalStore
from app.schemas.runtime import ApprovalDecision, ApprovalOut, ApprovalStatus

log = logging.getLogger(__name__)
POLL_S = 3.0
DEFAULT_TTL_S = 24 * 3600

NotifyFn = Callable[..., Awaitable[Any]]
Validator = Callable[[str, dict[str, Any]], None]  # raises InvalidRequestError


@dataclass(frozen=True)
class SessionGrant:
    id: str
    project_id: str | None
    tool_name: str
    created_at: datetime


class SessionGrants:
    """'Approve for session': scoped to one tool in one project and gone when the backend restarts."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._grants: dict[str, SessionGrant] = {}

    def add(self, project_id: str | None, tool_name: str) -> SessionGrant:
        for g in self._grants.values():
            if g.project_id == project_id and g.tool_name == tool_name:
                return g
        grant = SessionGrant(new_id("grant"), project_id, tool_name, self._clock.now())
        self._grants[grant.id] = grant
        return grant

    def has(self, project_id: str | None, tool_name: str) -> bool:
        return any(g.project_id == project_id and g.tool_name == tool_name for g in self._grants.values())

    def revoke(self, grant_id: str) -> bool:
        return self._grants.pop(grant_id, None) is not None

    def clear(self) -> None:
        self._grants.clear()

    def list_grants(self) -> list[SessionGrant]:
        return list(self._grants.values())


class ApprovalService:
    def __init__(
        self,
        store: ApprovalStore,
        bus: EventBus,
        grants: SessionGrants,
        notify: NotifyFn | None = None,
        clock: Clock | None = None,
        validator: Validator | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self.grants = grants
        self._notify = notify
        self._clock = clock or SystemClock()
        self._validator = validator
        self._wakeups: dict[str, asyncio.Event] = {}

    def set_validator(self, validator: Validator) -> None:
        self._validator = validator

    async def request(
        self,
        *,
        project_id: str | None,
        run_id: str | None,
        task_id: str | None,
        agent_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
        risk: RiskLevel,
        impact: str,
        session_grantable: bool,
        tainted: bool,
        taint_sources: list[str],
        tool_call_id: str | None = None,
    ) -> ApprovalOut:
        approval = await self._store.create(
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=redact(arguments),
            reason=reason[:500],
            risk_level=risk.value,
            impact=impact[:1000],
            session_grantable=session_grantable,
            tainted=tainted,
            taint_sources=taint_sources[:10],
            tool_call_id=tool_call_id,
        )
        self._wakeups[approval.id] = asyncio.Event()
        await self._bus.emit(
            EventType.APPROVAL_REQUIRED,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            payload={
                "approval_id": approval.id,
                "tool": tool_name,
                "risk": risk.value,
                "reason": reason[:200],
                "tainted": tainted,
            },
        )
        if self._notify:
            try:
                await self._notify(
                    "approval_required",
                    f"Approval needed: {tool_name}",
                    reason[:200] or impact[:200],
                    project_id=project_id,
                    ref={"approval_id": approval.id, "run_id": run_id},
                )
            except Exception:
                log.exception("approval notification failed")
        return approval

    async def wait(self, approval_id: str, *, ttl_s: float | None = DEFAULT_TTL_S) -> ApprovalOut:
        """Block until decided. The row decides; the event just wakes us sooner. After ``ttl_s`` the
        approval expires and is treated as a denial."""
        event = self._wakeups.setdefault(approval_id, asyncio.Event())
        loop = asyncio.get_running_loop()
        deadline = None if ttl_s is None else loop.time() + ttl_s
        try:
            while True:
                current = await self._store.get(approval_id)
                if current.status is not ApprovalStatus.PENDING:
                    return current
                if deadline is not None and loop.time() >= deadline:
                    return await self._expire(approval_id)
                timeout = POLL_S if deadline is None else max(0.01, min(POLL_S, deadline - loop.time()))
                event.clear()
                try:
                    await asyncio.wait_for(event.wait(), timeout=timeout)
                except TimeoutError:
                    continue  # poll the row again (covers decisions made in another process)
        finally:
            self._wakeups.pop(approval_id, None)

    async def _expire(self, approval_id: str) -> ApprovalOut:
        try:
            done = await self._store.decide(
                approval_id, ApprovalStatus.EXPIRED, decided_by="system", note="Expired without a decision"
            )
        except ConflictError:
            return await self._store.get(approval_id)
        await self._bus.emit(
            EventType.APPROVAL_DENIED,
            project_id=done.project_id,
            run_id=done.run_id,
            task_id=done.task_id,
            agent_id=done.agent_id,
            actor="system",
            payload={"approval_id": approval_id, "tool": done.tool_name, "reason": "expired"},
        )
        return done

    async def decide(
        self, approval_id: str, decision: ApprovalDecision, *, actor: str = "user"
    ) -> ApprovalOut:
        current = await self._store.get(approval_id)
        if current.status is not ApprovalStatus.PENDING:
            raise ConflictError(
                f"This approval was already {current.status.value.lower().replace('_', ' ')}."
            )
        if decision.decision == "approve_session" and not current.session_grantable:
            raise InvalidRequestError(
                "This action cannot be approved for the whole session. Approve it once, or deny it."
            )
        if decision.decision == "deny" and decision.edited_arguments is not None:
            raise InvalidRequestError("A denied action cannot carry edited arguments.")
        edited = decision.edited_arguments
        if edited is not None and self._validator is not None:
            self._validator(current.tool_name, edited)  # surfaces mistakes to the human before the run wakes

        status = {
            "approve_once": ApprovalStatus.APPROVED_ONCE,
            "approve_session": ApprovalStatus.APPROVED_SESSION,
            "deny": ApprovalStatus.DENIED,
        }[decision.decision]
        done = await self._store.decide(
            approval_id,
            status,
            decided_by=actor,
            note=decision.note,
            edited_arguments=redact(edited) if edited is not None else None,
        )
        if status is ApprovalStatus.APPROVED_SESSION:
            self.grants.add(done.project_id, done.tool_name)
        event_type = (
            EventType.APPROVAL_DENIED if status is ApprovalStatus.DENIED else EventType.APPROVAL_GRANTED
        )
        await self._bus.emit(
            event_type,
            project_id=done.project_id,
            run_id=done.run_id,
            task_id=done.task_id,
            agent_id=done.agent_id,
            actor=actor,
            payload={
                "approval_id": approval_id,
                "tool": done.tool_name,
                "decision": decision.decision,
                "edited": edited is not None,
            },
        )
        if edited is not None:
            await self._bus.emit(
                EventType.APPROVAL_EDITED,
                project_id=done.project_id,
                run_id=done.run_id,
                actor=actor,
                payload={"approval_id": approval_id, "tool": done.tool_name},
            )
        waiter = self._wakeups.get(approval_id)
        if waiter:
            waiter.set()
        return done

    async def cancel_for_runs(self, run_ids: list[str], note: str = "The run ended") -> int:
        cancelled = await self._store.cancel_open_for_runs(run_ids, note)
        for waiter in list(self._wakeups.values()):
            waiter.set()  # waiters re-read their row; unaffected ones simply go back to waiting
        return cancelled

    async def get(self, approval_id: str) -> ApprovalOut:
        return await self._store.get(approval_id)

    async def list_approvals(self, **kw: Any) -> list[ApprovalOut]:
        return await self._store.list_approvals(**kw)

    def is_session_granted(self, project_id: str | None, tool_name: str) -> bool:
        return self.grants.has(project_id, tool_name)
