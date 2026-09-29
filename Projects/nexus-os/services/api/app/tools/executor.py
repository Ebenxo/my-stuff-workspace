"""ToolExecutor: the single gate between an agent's *proposal* and any side effect.

    resolve → agent allow-list → validate arguments → assess risk → policy → (approval) → execute → log

Nothing else in the codebase calls a tool handler. Model output is only ever a proposal.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.core.clock import Clock, SystemClock
from app.core.errors import InvalidRequestError
from app.core.risk import RiskLevel, max_risk
from app.core.security import redact, redact_text
from app.core.trust import scan_for_injection
from app.events.bus import EventBus
from app.events.types import EventType
from app.permissions.approvals import ApprovalService
from app.permissions.policy import PolicyInput, RiskAssessment, Verdict, evaluate
from app.permissions.taint import TaintTracker
from app.repositories.runtime_store import ToolCallStore, ToolRowStore
from app.schemas.agents import AgentDefinition
from app.schemas.common import PermissionLevel
from app.schemas.runtime import ApprovalOut, ApprovalStatus, ToolCallStatus
from app.tools.base import ToolContext, ToolDefinition, ToolError
from app.tools.registry import ToolRegistry

log = logging.getLogger(__name__)
OutcomeStatus = Literal["ok", "denied", "failed", "invalid"]
WaitHook = Callable[[ApprovalOut | None], Awaitable[None]]


@dataclass
class ExecContext:
    """Per-run state the executor needs. ``taint`` is shared with the runner so provenance accumulates."""

    project_id: str
    run_id: str | None
    task_id: str | None
    objective_id: str | None
    agent: AgentDefinition
    permission_level: PermissionLevel
    tool_context: ToolContext
    taint: TaintTracker = field(default_factory=TaintTracker)
    unattended: bool = False
    on_wait: WaitHook | None = None  # called with the approval when parking, and None when resuming
    approval_ttl_s: float | None = 24 * 3600


@dataclass
class ToolOutcome:
    status: OutcomeStatus
    tool: str
    text: str  # what the agent is told (redacted, size-capped)
    tool_call_id: str | None = None
    error_code: str | None = None
    risk: RiskLevel = RiskLevel.SAFE
    untrusted: bool = False
    source: str | None = None
    approval_id: str | None = None
    duration_ms: int = 0
    flags: list[str] = field(default_factory=list)
    data: Any = None
    retryable: bool = False


def _cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…[truncated {len(text) - limit:,} characters]", True


def _brief(args: dict[str, Any], limit: int = 600) -> dict[str, Any]:
    """Arguments for events and the database: redacted and shortened."""
    clean = redact(args)
    out: dict[str, Any] = {}
    for k, v in clean.items():
        s = v if isinstance(v, str) else json.dumps(v, default=str)
        out[k] = s if len(s) <= limit else s[:limit] + f"…[+{len(s) - limit} chars]"
    return out


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        approvals: ApprovalService,
        calls: ToolCallStore,
        bus: EventBus,
        tool_rows: ToolRowStore | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._registry = registry
        self._approvals = approvals
        self._calls = calls
        self._bus = bus
        self._rows = tool_rows
        self._clock = clock or SystemClock()

    async def _disabled(self) -> set[str]:
        return await self._rows.disabled_names() if self._rows else set()

    def validate_arguments(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Schema check only (used to vet a human's edit before it wakes a run)."""
        tool = self._registry.get(tool_name)
        if tool is None:
            raise InvalidRequestError(f"Unknown tool {tool_name}.")
        try:
            tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            raise InvalidRequestError(_describe(exc)) from None

    async def _emit(self, type_: EventType, ectx: ExecContext, payload: dict[str, Any]) -> None:
        await self._bus.emit(
            type_,
            project_id=ectx.project_id,
            objective_id=ectx.objective_id,
            task_id=ectx.task_id,
            run_id=ectx.run_id,
            agent_id=ectx.agent.id,
            payload=payload,
        )

    async def _deny(
        self,
        ectx: ExecContext,
        name: str,
        args: dict[str, Any],
        summary: str,
        risk: RiskLevel,
        message: str,
        *,
        code: str,
        call_id: str | None = None,
    ) -> ToolOutcome:
        if call_id is None:
            row = await self._calls.create(
                run_id=ectx.run_id,
                task_id=ectx.task_id,
                project_id=ectx.project_id,
                tool_name=name,
                summary=summary,
                arguments=_brief(args),
                risk=risk,
                status=ToolCallStatus.DENIED,
            )
            call_id = row.id
        await self._calls.update(
            call_id,
            status=ToolCallStatus.DENIED,
            error={"code": code, "message": message},
            finished_at=self._clock.now(),
        )
        await self._emit(
            EventType.TOOL_DENIED,
            ectx,
            {"tool": name, "tool_call_id": call_id, "code": code, "reason": message[:300]},
        )
        return ToolOutcome("denied", name, message, tool_call_id=call_id, error_code=code, risk=risk)

    async def execute(
        self, ectx: ExecContext, tool_name: str, arguments: dict[str, Any], *, summary: str = ""
    ) -> ToolOutcome:
        summary = summary[:300]
        registry_tool = self._registry.get(tool_name)
        allowed = {
            t.name for t in self._registry.allowed_for(ectx.agent.tools, disabled=await self._disabled())
        }
        # 1-2. Unknown tools and tools outside this agent's allow-list are indistinguishable to the agent.
        if registry_tool is None or tool_name not in allowed:
            return await self._deny(
                ectx,
                tool_name,
                arguments,
                summary,
                RiskLevel.SAFE,
                f"'{tool_name}' is not an available tool. Available tools: {', '.join(sorted(allowed)) or 'none'}.",
                code="unknown_tool",
            )
        tool = registry_tool

        # 3. Validate arguments (errors never echo the offending values).
        try:
            args = tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            row = await self._calls.create(
                run_id=ectx.run_id,
                task_id=ectx.task_id,
                project_id=ectx.project_id,
                tool_name=tool_name,
                summary=summary,
                arguments=_brief(arguments),
                risk=tool.risk_level,
                status=ToolCallStatus.FAILED,
            )
            msg = f"Invalid arguments for {tool_name}: {_describe(exc)}. Expected: {tool.signature()}"
            await self._calls.update(
                row.id, error={"code": "invalid_arguments", "message": msg}, finished_at=self._clock.now()
            )
            await self._emit(
                EventType.TOOL_FAILED,
                ectx,
                {"tool": tool_name, "tool_call_id": row.id, "code": "invalid_arguments"},
            )
            return ToolOutcome(
                "invalid",
                tool_name,
                msg,
                tool_call_id=row.id,
                error_code="invalid_arguments",
                risk=tool.risk_level,
            )

        # 4. Assess this particular call.
        assessment = self._assess(tool, ectx, args)
        effective = max_risk(tool.risk_level, assessment.level)
        impact = (
            assessment.impact
            or (tool.describe_impact(args) if tool.describe_impact else "")
            or f"Runs {tool_name}."
        )
        row = await self._calls.create(
            run_id=ectx.run_id,
            task_id=ectx.task_id,
            project_id=ectx.project_id,
            tool_name=tool_name,
            summary=summary,
            arguments=_brief(arguments),
            risk=effective,
            status=ToolCallStatus.PROPOSED,
        )
        call_id = row.id
        await self._emit(
            EventType.TOOL_CALLED,
            ectx,
            {
                "tool": tool_name,
                "tool_call_id": call_id,
                "risk": effective.value,
                "summary": summary,
                "arguments": _brief(arguments, 200),
            },
        )

        # 5. Policy: a pure function of facts, never of model text.
        decision = evaluate(
            PolicyInput(
                tool_name=tool_name,
                static_risk=tool.risk_level,
                tool_always_asks=tool.requires_approval,
                assessment=assessment,
                permission_level=ectx.permission_level,
                agent_max_risk=ectx.agent.permissions.max_risk,
                agent_may_request_approval=ectx.agent.permissions.may_request_approval,
                unattended=ectx.unattended,
                tainted=ectx.taint.tainted,
                session_granted=self._approvals.is_session_granted(ectx.project_id, tool_name),
            )
        )
        if decision.verdict is Verdict.DENY:
            await self._bus.emit(
                EventType.POLICY_DENIED,
                project_id=ectx.project_id,
                run_id=ectx.run_id,
                agent_id=ectx.agent.id,
                payload={"tool": tool_name, "reasons": decision.reasons[:3]},
            )
            return await self._deny(
                ectx,
                tool_name,
                arguments,
                summary,
                effective,
                "; ".join(decision.reasons),
                code="policy_denied",
                call_id=call_id,
            )

        # 6. Approval: park until a human decides.
        approval_id: str | None = None
        if decision.verdict is Verdict.REQUIRE_APPROVAL:
            try:
                # Status first, then the approval: anyone who can see the approval sees a coherent tool call.
                await self._calls.update(call_id, status=ToolCallStatus.AWAITING_APPROVAL)
                approval = await self._approvals.request(
                    project_id=ectx.project_id,
                    run_id=ectx.run_id,
                    task_id=ectx.task_id,
                    agent_id=ectx.agent.id,
                    tool_name=tool_name,
                    arguments=arguments,
                    reason=summary or f"{ectx.agent.name} wants to run {tool_name}",
                    risk=effective,
                    impact=impact,
                    session_grantable=decision.session_grantable,
                    tainted=ectx.taint.tainted,
                    taint_sources=ectx.taint.sources,
                    tool_call_id=call_id,
                )
                approval_id = approval.id
                await self._calls.update(call_id, approval_id=approval.id)
                if ectx.on_wait:
                    await ectx.on_wait(approval)
                try:
                    decided = await self._approvals.wait(approval.id, ttl_s=ectx.approval_ttl_s)
                finally:
                    if ectx.on_wait:
                        await ectx.on_wait(None)
            except asyncio.CancelledError:
                # Cancelled at any point while asking: the call must not be left "awaiting approval".
                await self._calls.update(
                    call_id,
                    status=ToolCallStatus.FAILED,
                    error={
                        "code": "cancelled",
                        "message": "The run was cancelled while waiting for approval.",
                    },
                    finished_at=self._clock.now(),
                )
                raise
            if decided.status not in (ApprovalStatus.APPROVED_ONCE, ApprovalStatus.APPROVED_SESSION):
                why = {
                    "DENIED": "The user denied this action",
                    "EXPIRED": "Nobody answered in time, so the action was not run",
                    "CANCELLED": "The run ended before a decision",
                }.get(decided.status.value, "Not approved")
                note = f" ({decided.decision_note})" if decided.decision_note else ""
                return await self._deny(
                    ectx,
                    tool_name,
                    arguments,
                    summary,
                    effective,
                    f"{why}{note}. Choose another approach or ask the user.",
                    code="approval_denied",
                    call_id=call_id,
                )
            if decided.edited_arguments is not None:
                # 6b. A person edited the action: it must pass validation and DENY rules again.
                try:
                    args = tool.input_schema.model_validate(decided.edited_arguments)
                except ValidationError as exc:
                    return await self._deny(
                        ectx,
                        tool_name,
                        arguments,
                        summary,
                        effective,
                        f"The edited action was invalid: {_describe(exc)}",
                        code="edit_invalid",
                        call_id=call_id,
                    )
                again = self._assess(tool, ectx, args)
                if again.deny_reason:
                    return await self._deny(
                        ectx,
                        tool_name,
                        arguments,
                        summary,
                        effective,
                        f"The edited action was refused: {again.deny_reason}",
                        code="edit_denied",
                        call_id=call_id,
                    )
                arguments = decided.edited_arguments
                effective = max_risk(tool.risk_level, again.level)

        # 7. Execute with a timeout; failures are results the agent can act on.
        await self._calls.update(call_id, status=ToolCallStatus.RUNNING, risk_level=effective.value)
        started = time.monotonic()
        try:
            raw = await asyncio.wait_for(tool.handler(ectx.tool_context, args), timeout=tool.timeout_s)
        except TimeoutError:
            return await self._fail(
                ectx,
                tool,
                call_id,
                started,
                "timeout",
                f"{tool_name} took longer than {tool.timeout_s:g}s and was stopped.",
                effective,
                approval_id,
                retryable=True,
            )
        except ToolError as exc:
            return await self._fail(
                ectx,
                tool,
                call_id,
                started,
                exc.code,
                exc.message,
                effective,
                approval_id,
                retryable=exc.retryable,
            )
        except asyncio.CancelledError:
            await self._calls.update(
                call_id,
                status=ToolCallStatus.FAILED,
                error={"code": "cancelled", "message": "The run was cancelled."},
                finished_at=self._clock.now(),
            )
            raise
        except Exception as exc:
            log.exception("tool %s crashed", tool_name)
            return await self._fail(
                ectx,
                tool,
                call_id,
                started,
                "internal_error",
                f"{tool_name} failed unexpectedly ({type(exc).__name__}).",
                effective,
                approval_id,
            )

        # 8. Result: redact, cap, taint if external, scan for injection, log.
        duration = int((time.monotonic() - started) * 1000)
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str, ensure_ascii=False)
        text = redact_text(text)
        shown, cut = _cap(text, tool.max_output_chars)
        source = tool.source_label(args) if tool.source_label else f"tool:{tool_name}"
        flags: list[str] = []
        if tool.returns_untrusted:
            ectx.taint.add(source)
            found = scan_for_injection(_scannable(raw, text))
            if found:
                flags = [f.label for f in found]
                await self._bus.emit(
                    EventType.SECURITY_FLAG,
                    project_id=ectx.project_id,
                    run_id=ectx.run_id,
                    agent_id=ectx.agent.id,
                    payload={
                        "tool": tool_name,
                        "source": source,
                        "findings": flags,
                        "excerpt": found[0].excerpt,
                    },
                )
        await self._calls.update(
            call_id,
            status=ToolCallStatus.SUCCEEDED,
            duration_ms=duration,
            finished_at=self._clock.now(),
            result={"text": shown[:4000], "truncated": cut or len(shown) > 4000},
            provenance={"taint": ectx.taint.sources, "flags": flags},
        )
        await self._emit(
            EventType.TOOL_COMPLETED,
            ectx,
            {
                "tool": tool_name,
                "tool_call_id": call_id,
                "duration_ms": duration,
                "risk": effective.value,
                "untrusted": tool.returns_untrusted,
                "flags": flags,
            },
        )
        return ToolOutcome(
            "ok",
            tool_name,
            shown,
            tool_call_id=call_id,
            risk=effective,
            untrusted=tool.returns_untrusted,
            source=source,
            approval_id=approval_id,
            duration_ms=duration,
            flags=flags,
            data=raw,
        )

    def _assess(self, tool: ToolDefinition, ectx: ExecContext, args: Any) -> RiskAssessment:
        if tool.assess_risk is None:
            return RiskAssessment(
                level=tool.risk_level, impact=tool.describe_impact(args) if tool.describe_impact else ""
            )
        try:
            return tool.assess_risk(ectx.tool_context, args)
        except Exception:
            log.exception("risk assessment for %s failed", tool.name)
            return RiskAssessment(
                level=RiskLevel.HIGH,
                always_ask=True,
                impact="Could not assess this action's risk, so a person must review it.",
            )

    async def _fail(
        self,
        ectx: ExecContext,
        tool: ToolDefinition,
        call_id: str,
        started: float,
        code: str,
        message: str,
        risk: RiskLevel,
        approval_id: str | None,
        *,
        retryable: bool = False,
    ) -> ToolOutcome:
        duration = int((time.monotonic() - started) * 1000)
        message = redact_text(message)
        await self._calls.update(
            call_id,
            status=ToolCallStatus.FAILED,
            duration_ms=duration,
            finished_at=self._clock.now(),
            error={"code": code, "message": message},
        )
        await self._emit(
            EventType.TOOL_FAILED,
            ectx,
            {"tool": tool.name, "tool_call_id": call_id, "code": code, "message": message[:300]},
        )
        return ToolOutcome(
            "failed",
            tool.name,
            message,
            tool_call_id=call_id,
            error_code=code,
            risk=risk,
            approval_id=approval_id,
            duration_ms=duration,
            retryable=retryable,
        )


def _scannable(raw: Any, fallback: str) -> str:
    """The real text to scan for injection. JSON-encoding a result turns newlines into ``\\n`` and hides
    word boundaries (``\\nIgnore``), so scan the string values themselves, not their serialisation."""
    parts: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)
        elif isinstance(v, (list, tuple)):
            for item in v:
                walk(item)

    walk(raw)
    return "\n".join(parts) if parts else fallback


def _describe(exc: ValidationError) -> str:
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False, include_context=False)
    ]
    return "; ".join(parts)[:500]
