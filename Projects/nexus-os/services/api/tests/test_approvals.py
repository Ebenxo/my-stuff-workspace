from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI

from app.core.errors import ConflictError, InvalidRequestError
from app.core.risk import RiskLevel
from app.permissions.approvals import ApprovalService
from app.repositories.events import EventFilter
from app.schemas.runtime import ApprovalDecision, ApprovalStatus


@pytest.fixture
def svc(app: FastAPI) -> ApprovalService:
    return app.state.container.approvals  # type: ignore[no-any-return]


async def audit_types(app: FastAPI, project_id: str = "proj_a") -> list[str]:
    events = await app.state.container.bus.query(EventFilter(project_id=project_id))
    return [e.type for e in events if e.type != "NOTIFICATION_CREATED"]


async def request(svc: ApprovalService, **over: Any) -> Any:
    base: dict[str, Any] = dict(
        project_id="proj_a",
        run_id="run_1",
        task_id=None,
        agent_id="agent_x",
        tool_name="run_command",
        arguments={"argv": ["ls"]},
        reason="List files",
        risk=RiskLevel.HIGH,
        impact="Runs a program",
        session_grantable=True,
        tainted=False,
        taint_sources=[],
    )
    return await svc.request(**{**base, **over})


async def test_request_persists_emits_and_notifies(svc: ApprovalService, app: FastAPI) -> None:
    a = await request(
        svc, arguments={"argv": ["curl"], "api_key": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123"}
    )
    assert a.status is ApprovalStatus.PENDING and a.risk_level is RiskLevel.HIGH
    assert "sk-ant" not in str(a.arguments)  # arguments are redacted before they are stored
    assert await audit_types(app) == ["APPROVAL_REQUIRED"]
    notes = await app.state.container.notifications.list_all()
    assert notes[0].kind == "approval_required" and notes[0].ref["approval_id"] == a.id


async def test_approve_once_wakes_the_waiting_run(svc: ApprovalService) -> None:
    a = await request(svc)
    waiter = asyncio.create_task(svc.wait(a.id))
    await asyncio.sleep(0.05)
    assert not waiter.done()
    await svc.decide(a.id, ApprovalDecision(decision="approve_once"))
    done = await asyncio.wait_for(waiter, 2)
    assert done.status is ApprovalStatus.APPROVED_ONCE and done.decided_by == "user"
    assert not svc.is_session_granted("proj_a", "run_command")  # once means once


async def test_approve_for_session_creates_a_scoped_revocable_grant(svc: ApprovalService) -> None:
    a = await request(svc)
    await svc.decide(a.id, ApprovalDecision(decision="approve_session"))
    assert svc.is_session_granted("proj_a", "run_command")
    assert not svc.is_session_granted("proj_b", "run_command")  # other project
    assert not svc.is_session_granted("proj_a", "delete_file")  # other tool
    (grant,) = svc.grants.list_grants()
    assert svc.grants.revoke(grant.id) and not svc.is_session_granted("proj_a", "run_command")
    assert not svc.grants.revoke(grant.id)


async def test_session_approval_refused_when_not_grantable(svc: ApprovalService) -> None:
    a = await request(svc, risk=RiskLevel.VERY_HIGH, session_grantable=False)
    with pytest.raises(InvalidRequestError, match="whole session"):
        await svc.decide(a.id, ApprovalDecision(decision="approve_session"))
    assert (await svc.get(a.id)).status is ApprovalStatus.PENDING  # the refusal did not consume the approval
    assert not svc.is_session_granted("proj_a", "run_command")


async def test_deny_wakes_the_run_with_a_denial_and_emits_an_event(
    svc: ApprovalService, app: FastAPI
) -> None:
    a = await request(svc)
    waiter = asyncio.create_task(svc.wait(a.id))
    await svc.decide(a.id, ApprovalDecision(decision="deny", note="not now"))
    done = await asyncio.wait_for(waiter, 2)
    assert done.status is ApprovalStatus.DENIED and done.decision_note == "not now"
    assert await audit_types(app) == ["APPROVAL_REQUIRED", "APPROVAL_DENIED"]


async def test_a_decision_can_only_be_made_once_even_concurrently(svc: ApprovalService) -> None:
    a = await request(svc)
    results = await asyncio.gather(
        svc.decide(a.id, ApprovalDecision(decision="approve_once")),
        svc.decide(a.id, ApprovalDecision(decision="deny")),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ConflictError) for r in results) == 1
    assert sum(not isinstance(r, Exception) for r in results) == 1
    final = await svc.get(a.id)
    with pytest.raises(ConflictError, match="already"):
        await svc.decide(a.id, ApprovalDecision(decision="deny"))
    assert (await svc.get(a.id)).status is final.status  # unchanged by the late attempt


async def test_edited_arguments_are_validated_stored_and_audited(svc: ApprovalService, app: FastAPI) -> None:
    def validator(tool: str, args: dict[str, Any]) -> None:
        if "argv" not in args:
            raise InvalidRequestError("argv is required")

    svc.set_validator(validator)
    a = await request(svc)
    with pytest.raises(InvalidRequestError, match="argv is required"):
        await svc.decide(a.id, ApprovalDecision(decision="approve_once", edited_arguments={"oops": 1}))
    assert (await svc.get(a.id)).status is ApprovalStatus.PENDING
    done = await svc.decide(
        a.id, ApprovalDecision(decision="approve_once", edited_arguments={"argv": ["ls", "-l"]})
    )
    assert done.edited_arguments == {"argv": ["ls", "-l"]} and done.arguments == {
        "argv": ["ls"]
    }  # original kept for audit
    assert "APPROVAL_EDITED" in await audit_types(app)
    b = await request(svc)
    with pytest.raises(InvalidRequestError, match="denied"):
        await svc.decide(b.id, ApprovalDecision(decision="deny", edited_arguments={"argv": ["x"]}))


async def test_unanswered_approvals_expire_and_read_as_denials(svc: ApprovalService, app: FastAPI) -> None:
    a = await request(svc)
    done = await svc.wait(a.id, ttl_s=0.05)
    assert done.status is ApprovalStatus.EXPIRED
    with pytest.raises(ConflictError):
        await svc.decide(a.id, ApprovalDecision(decision="approve_once"))
    assert "APPROVAL_DENIED" in [
        e.type for e in await app.state.container.bus.query(EventFilter(project_id="proj_a"))
    ]


async def test_waiting_survives_a_missed_wakeup_by_polling_the_row(
    svc: ApprovalService, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.permissions.approvals as mod

    monkeypatch.setattr(mod, "POLL_S", 0.05)
    a = await request(svc)
    waiter = asyncio.create_task(svc.wait(a.id))
    await asyncio.sleep(0.02)
    # Decide straight in the store, bypassing the service (as another process would): no event is set.
    await app.state.container.approval_store.decide(
        a.id, ApprovalStatus.APPROVED_ONCE, decided_by="other-process"
    )
    done = await asyncio.wait_for(waiter, 2)
    assert done.status is ApprovalStatus.APPROVED_ONCE


async def test_cancelling_a_run_cancels_its_open_approvals(svc: ApprovalService) -> None:
    a = await request(svc, run_id="run_dead")
    b = await request(svc, run_id="run_alive")
    waiter = asyncio.create_task(svc.wait(a.id))
    await svc.cancel_for_runs(["run_dead"])
    assert (await asyncio.wait_for(waiter, 2)).status is ApprovalStatus.CANCELLED
    assert (await svc.get(b.id)).status is ApprovalStatus.PENDING


async def test_listing_filters(svc: ApprovalService) -> None:
    a = await request(svc)
    await request(svc, project_id="proj_b")
    await svc.decide(a.id, ApprovalDecision(decision="deny"))
    assert len(await svc.list_approvals(status="PENDING")) == 1
    assert len(await svc.list_approvals(project_id="proj_a")) == 1
    assert len(await svc.list_approvals()) == 2
