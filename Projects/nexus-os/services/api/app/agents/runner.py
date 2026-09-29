"""AgentRunner: one agent, one task, a bounded and recoverable loop.

    model turn (structured AgentStep) -> tool proposal -> ToolExecutor (policy, approval, sandbox) -> observation

Guarantees, each covered by a test:
- every limit is enforced: steps, tool calls, tokens, wall-clock (time spent waiting for a person is
  not counted), and repeated identical calls (nudge, then stop);
- the run is checkpointed after every step and resumable after a crash, a restart or a human answer;
  an action that was in flight when the process died is never silently re-executed;
- cancelling stops the loop, cancels open approvals and records the run as cancelled;
- model output is only ever a *proposal*: nothing runs except through the ToolExecutor;
- hidden reasoning is never requested, stored or shown; only the public step summary is kept;
- artifacts named in the final result must have been created by this run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from app.agents.prompt import ContextBlock, PromptBuilder
from app.agents.state import Observation, StepRecord, dump_records, load_records
from app.core.failures import FailureCategory
from app.core.ids import new_id
from app.core.security import redact_text
from app.events.bus import EventBus
from app.events.types import EventType
from app.permissions.approvals import ApprovalService
from app.permissions.taint import TaintTracker
from app.providers.gateway import CallContext, GatewayError, LLMGateway
from app.providers.router import TaskClass
from app.providers.types import GenerateRequest
from app.repositories.runtime_store import AgentStore, RunStore, ToolRowStore
from app.schemas.agents import (
    AgentDefinition,
    AgentStep,
    ArtifactRef,
    AskHumanAction,
    FinishAction,
    OutputRef,
    TaskResult,
    ToolCallAction,
)
from app.schemas.common import PermissionLevel
from app.schemas.runtime import AgentRunOut, ApprovalOut, RunStatus
from app.tools.context import ToolContextFactory
from app.tools.executor import ExecContext, ToolExecutor, ToolOutcome
from app.tools.registry import ToolRegistry

log = logging.getLogger(__name__)

MAX_STEP_TOKENS = 8192
NUDGE_AFTER_REPEATS = 3
ABORT_AFTER_REPEATS = 5
REPEAT_WINDOW = 10
TOKEN_WARN_FRACTION = 0.85

ContextProvider = Callable[[AgentDefinition, str, str], Awaitable[list[ContextBlock]]]


@dataclass
class RunRequest:
    agent: AgentDefinition
    project_id: str
    prompt: str
    context: list[ContextBlock] = field(default_factory=list)
    model: str | None = None  # manual override "<provider_id>:<model>"
    private: bool = False
    objective_id: str | None = None
    task_id: str | None = None
    permission_level: PermissionLevel = PermissionLevel.BALANCED
    unattended: bool = False
    task_class: TaskClass = TaskClass.GENERAL
    approval_ttl_s: float | None = 24 * 3600

    def to_json(self) -> dict[str, Any]:
        """What is stored for resumption. Text is redacted first: a pasted key never reaches the database."""
        return {
            "agent_id": self.agent.id,
            "project_id": self.project_id,
            "prompt": redact_text(self.prompt),
            "context": [{"source": b.source, "text": redact_text(b.text)} for b in self.context],
            "model": self.model,
            "private": self.private,
            "objective_id": self.objective_id,
            "task_id": self.task_id,
            "permission_level": self.permission_level.value,
            "unattended": self.unattended,
            "task_class": self.task_class.value,
            "approval_ttl_s": self.approval_ttl_s,
        }

    @classmethod
    def from_json(cls, agent: AgentDefinition, data: dict[str, Any]) -> RunRequest:
        return cls(
            agent=agent,
            project_id=data["project_id"],
            prompt=data["prompt"],
            context=[ContextBlock(c["source"], c["text"]) for c in data.get("context", [])],
            model=data.get("model"),
            private=bool(data.get("private", False)),
            objective_id=data.get("objective_id"),
            task_id=data.get("task_id"),
            permission_level=PermissionLevel(data.get("permission_level", "balanced")),
            unattended=bool(data.get("unattended", False)),
            task_class=TaskClass(data.get("task_class", "general")),
            approval_ttl_s=data.get("approval_ttl_s"),
        )


@dataclass
class RunOutcome:
    run: AgentRunOut
    result: TaskResult | None = None
    question: str | None = None
    options: list[str] = field(default_factory=list)

    @property
    def status(self) -> RunStatus:
        return self.run.status

    @property
    def ok(self) -> bool:
        return self.run.status is RunStatus.COMPLETED


@dataclass
class _State:
    records: list[StepRecord]
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model: str | None = None
    started: float = field(default_factory=time.monotonic)
    paused_at: float | None = None
    paused_total: float = 0.0
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)
    limit_refusals: int = 0
    token_warned: bool = False

    def active_s(self) -> float:
        now = time.monotonic()
        paused = self.paused_total + ((now - self.paused_at) if self.paused_at is not None else 0.0)
        return max(0.0, now - self.started - paused)

    def pause(self) -> None:
        if self.paused_at is None:
            self.paused_at = time.monotonic()

    def unpause(self) -> None:
        if self.paused_at is not None:
            self.paused_total += time.monotonic() - self.paused_at
            self.paused_at = None

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    def note_artifacts(self, refs: list[dict[str, Any]]) -> None:
        for ref in refs:
            self.artifacts[str(ref["artifact_id"])] = ref

    def taint_sources(self) -> list[str]:
        return [
            r.observation.source
            for r in self.records
            if r.observation and r.observation.untrusted and r.observation.source
        ]


@dataclass(frozen=True)
class _Stop:
    status: RunStatus
    category: FailureCategory
    code: str
    message: str


def _signature(action: dict[str, Any]) -> str:
    return f"{action.get('tool')}:{json.dumps(action.get('arguments', {}), sort_keys=True, default=str)}"


def _classify_reported_failure(records: list[StepRecord]) -> FailureCategory:
    """An agent said 'failed'. What was the last thing that went wrong?"""
    for rec in reversed(records):
        o = rec.observation
        if o is None or o.kind != "tool":
            continue
        if o.status == "denied":
            return FailureCategory.PERMISSION_DENIED
        if o.status in ("failed", "invalid"):
            return FailureCategory.TOOL_FAILURE
        break
    return FailureCategory.UNKNOWN


class AgentRunner:
    def __init__(
        self,
        *,
        gateway: LLMGateway,
        runs: RunStore,
        agents: AgentStore,
        executor: ToolExecutor,
        tools: ToolRegistry,
        tool_rows: ToolRowStore,
        tool_contexts: ToolContextFactory,
        approvals: ApprovalService,
        bus: EventBus,
        builder: PromptBuilder | None = None,
        context_provider: ContextProvider | None = None,
    ) -> None:
        self._gateway = gateway
        self._runs = runs
        self._agents = agents
        self._executor = executor
        self._tools = tools
        self._rows = tool_rows
        self._contexts = tool_contexts
        self._approvals = approvals
        self._bus = bus
        self._builder = builder or PromptBuilder()
        self._context_provider = context_provider
        self.shutting_down = False  # set on app shutdown: cancellation then means "park", not "cancel"

    def set_context_provider(self, provider: ContextProvider | None) -> None:
        self._context_provider = provider

    # ---- lifecycle ---------------------------------------------------------------------
    async def create(self, req: RunRequest, *, run_id: str | None = None) -> AgentRunOut:
        """Persist the run and announce it. Nothing executes yet."""
        if self._context_provider is not None:
            extra = await self._context_provider(req.agent, req.project_id, req.prompt)
            req = replace(req, context=[*req.context, *extra])
        run = await self._runs.create(
            run_id=run_id or new_id("run"),
            agent_id=req.agent.id,
            project_id=req.project_id,
            objective_id=req.objective_id,
            task_id=req.task_id,
            model=req.model,
            request=req.to_json(),
        )
        await self._emit(
            EventType.AGENT_STARTED,
            run.id,
            req,
            {
                "agent": req.agent.slug,
                "name": req.agent.name,
                "prompt": redact_text(req.prompt)[:300],
                "permission_level": req.permission_level.value,
                "private": req.private,
            },
        )
        return run

    async def run(self, req: RunRequest, *, run_id: str | None = None) -> RunOutcome:
        run = await self.create(req, run_id=run_id)
        return await self.execute(run.id, agent=req.agent)

    async def execute(self, run_id: str, *, agent: AgentDefinition | None = None) -> RunOutcome:
        """Run (or continue) a run from its checkpoint until it finishes, waits or stops."""
        run = await self._runs.get(run_id)
        request, raw = await self._runs.snapshot(run_id)
        if run.status.terminal:
            return RunOutcome(run, result=TaskResult.model_validate(run.result) if run.result else None)
        agent = agent or await self._agents.get(request["agent_id"])
        req = RunRequest.from_json(agent, request)
        state = _State(
            records=load_records(raw),
            tool_calls=run.tool_call_count,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            model=run.model,
        )
        for rec in state.records:
            if rec.observation:
                state.note_artifacts(rec.observation.artifact_refs)
        return await self._drive(run_id, req, state)

    async def prepare_resume(
        self, run_id: str, *, answer: str | None = None, agent: AgentDefinition | None = None
    ) -> AgentRunOut:
        """The synchronous half of resuming: validate, record the answer, reopen the run.

        Callers that run the loop in the background call this first so the response they return already
        shows the reopened run, then ``execute`` it.
        """
        run = await self._runs.get(run_id)
        request, raw = await self._runs.snapshot(run_id)
        records = load_records(raw)
        last = records[-1] if records else None
        if run.status is RunStatus.WAITING_INPUT:
            if not (answer and answer.strip()):
                raise ValueError("This run is waiting for an answer.")
            if last is not None and last.observation is None:
                last.observation = Observation(
                    kind="human", status="answered", text=redact_text(answer.strip())
                )
                await self._runs.save_progress(
                    run_id,
                    checkpoint=dump_records(records),
                    step_count=len(records),
                    tool_call_count=run.tool_call_count,
                    tokens_in=run.tokens_in,
                    tokens_out=run.tokens_out,
                    model=run.model,
                )
            reopened = await self._runs.reopen(run_id)
        elif run.status in (RunStatus.INTERRUPTED, RunStatus.FAILED, RunStatus.TIMED_OUT):
            reopened = await self._runs.restart(run_id)
        else:
            raise ValueError(f"A run that is {run.status.value.lower().replace('_', ' ')} cannot be resumed.")
        agent = agent or await self._agents.get(request["agent_id"])
        req = RunRequest.from_json(agent, request)
        await self._emit(
            EventType.AGENT_RESUMED, run_id, req, {"from": run.status.value, "attempt": reopened.attempt}
        )
        return reopened

    async def resume(
        self, run_id: str, *, answer: str | None = None, agent: AgentDefinition | None = None
    ) -> RunOutcome:
        """Continue a run that was interrupted, or that asked the person a question."""
        await self.prepare_resume(run_id, answer=answer, agent=agent)
        return await self.execute(run_id, agent=agent)

    async def abandon(self, run_id: str, *, agent: AgentDefinition | None = None) -> AgentRunOut:
        """Cancel a run that has no live process (interrupted, or waiting for an answer)."""
        run = await self._runs.get(run_id)
        if run.status.terminal:
            return run
        request, raw = await self._runs.snapshot(run_id)
        req = RunRequest.from_json(agent or await self._agents.get(request["agent_id"]), request)
        state = _State(
            records=load_records(raw),
            tool_calls=run.tool_call_count,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            model=run.model,
        )
        for rec in state.records:
            if rec.observation:
                state.note_artifacts(rec.observation.artifact_refs)
        await self._cancelled(run_id, req, state)
        return await self._runs.get(run_id)

    # ---- the loop ----------------------------------------------------------------------
    async def _drive(self, run_id: str, req: RunRequest, state: _State) -> RunOutcome:
        agent = req.agent
        dangling = state.records[-1] if state.records else None
        if dangling is not None and dangling.observation is None:
            if dangling.action_type in ("ask_human", "finish"):  # still waiting for the person's answer
                run = await self._runs.get(run_id)
                await self._runs.set_status(run_id, RunStatus.WAITING_INPUT)
                waiting = run.result or {}
                return RunOutcome(
                    await self._runs.get(run_id),
                    question=str(waiting.get("question", "")),
                    options=list(waiting.get("options", [])),
                )
            if dangling.action_type == "tool_call":
                # The process stopped mid-action. It may or may not have happened: never assume, never redo.
                dangling.observation = Observation(
                    kind="system",
                    status="interrupted",
                    tool=dangling.tool_name,
                    text=(
                        f"The previous action ({dangling.tool_name}) was interrupted by an application restart. "
                        "It may or may not have completed. Check the current state before repeating it."
                    ),
                )
                await self._save(run_id, state)
        tools = self._tools.allowed_for(agent.tools, disabled=await self._rows.disabled_names())
        if req.private:  # the model is never shown a tool it could not use (the executor refuses them too)
            tools = [t for t in tools if not t.reaches_outside]
        system = self._builder.system(
            agent, tools, max_steps=agent.max_steps, max_tool_calls=agent.max_tool_calls
        )
        tctx = await self._contexts.build(
            project_id=req.project_id,
            run_id=run_id,
            task_id=req.task_id,
            objective_id=req.objective_id,
            agent_id=agent.id,
            unattended=req.unattended,
            private=req.private,
        )
        ectx = ExecContext(
            project_id=req.project_id,
            run_id=run_id,
            task_id=req.task_id,
            objective_id=req.objective_id,
            agent=agent,
            permission_level=req.permission_level,
            tool_context=tctx,
            taint=TaintTracker.from_list(state.taint_sources()),
            unattended=req.unattended,
            on_wait=self._wait_hook(run_id, state),
            approval_ttl_s=req.approval_ttl_s,
        )
        try:
            return await self._loop(run_id, req, state, system, ectx)
        except asyncio.CancelledError:
            if self.shutting_down:
                await asyncio.shield(self._interrupted(run_id, req, state))
            else:
                await asyncio.shield(self._cancelled(run_id, req, state))
            raise
        except Exception as exc:
            log.exception("agent run %s crashed", run_id)
            return await self._stop(
                run_id,
                req,
                state,
                _Stop(
                    RunStatus.FAILED,
                    FailureCategory.UNKNOWN,
                    "internal_error",
                    f"The run stopped because of an internal error ({type(exc).__name__}).",
                ),
            )

    async def _loop(
        self, run_id: str, req: RunRequest, state: _State, system: str, ectx: ExecContext
    ) -> RunOutcome:
        agent = req.agent
        while True:
            stop = self._limit_hit(agent, state)
            if stop is not None:
                return await self._stop(run_id, req, state, stop)

            try:
                step, model = await self._model_step(run_id, req, state, system)
            except GatewayError as exc:
                return await self._stop(
                    run_id, req, state, _Stop(RunStatus.FAILED, exc.category, exc.code, exc.message)
                )
            except TimeoutError:
                return await self._stop(
                    run_id,
                    req,
                    state,
                    _Stop(
                        RunStatus.TIMED_OUT,
                        FailureCategory.TIMEOUT,
                        "runtime_limit",
                        f"Stopped after {agent.max_runtime_s}s of working time.",
                    ),
                )

            rec = StepRecord(
                n=len(state.records) + 1,
                summary=step.summary,
                action=step.action.model_dump(mode="json"),
                model=model,
            )
            state.records.append(rec)
            await self._save(run_id, state)  # the proposed action is durable before anything runs
            await self._emit(
                EventType.AGENT_STEP,
                run_id,
                req,
                {
                    "n": rec.n,
                    "summary": step.summary,
                    "action": rec.action_type,
                    "tool": rec.tool_name,
                    "model": model,
                },
            )

            action = step.action
            if isinstance(action, FinishAction):
                return await self._finish(run_id, req, state, action.result)
            if isinstance(action, AskHumanAction):
                return await self._ask(run_id, req, state, rec, action)
            if state.tool_calls >= agent.max_tool_calls:
                if state.limit_refusals >= 1:
                    return await self._stop(
                        run_id,
                        req,
                        state,
                        _Stop(
                            RunStatus.FAILED,
                            FailureCategory.TIMEOUT,
                            "tool_call_limit",
                            f"Stopped after {agent.max_tool_calls} tool calls without finishing.",
                        ),
                    )
                state.limit_refusals += 1
                rec.observation = Observation(
                    kind="system",
                    status="refused",
                    tool=action.tool,
                    text=f"The tool call limit ({agent.max_tool_calls}) is used up. Finish now with what you have.",
                )
            else:
                state.tool_calls += 1
                rec.observation = await self._run_tool(ectx, action, step.summary, state)

            abort = self._after_step(agent, state, rec)
            await self._save(run_id, state)
            if abort is not None:
                return await self._stop(run_id, req, state, abort)

    async def _model_step(
        self, run_id: str, req: RunRequest, state: _State, system: str
    ) -> tuple[AgentStep, str]:
        agent = req.agent
        messages = self._builder.messages(req.prompt, req.context, state.records)
        remaining_tokens = max(1, agent.token_budget - state.tokens)
        gen = GenerateRequest(
            model="",  # the gateway fills in the routed model
            messages=messages,
            system=system,
            temperature=agent.temperature,
            max_tokens=min(MAX_STEP_TOKENS, max(512, remaining_tokens)),
            reasoning=agent.reasoning_mode,
        )
        ctx = CallContext(
            purpose="agent",
            agent_id=agent.id,
            project_id=req.project_id,
            objective_id=req.objective_id,
            run_id=run_id,
            task_id=req.task_id,
            task_class=req.task_class,
            private=req.private,
            preferred_model=agent.preferred_model,
            fallback_models=tuple(agent.fallback_models),
            manual_override=req.model,
        )
        budget_s = max(1.0, agent.max_runtime_s - state.active_s())
        async with asyncio.timeout(budget_s):
            result, meta = await self._gateway.generate_structured(ctx, gen, AgentStep)
        state.tokens_in += meta.usage.input_tokens
        state.tokens_out += meta.usage.output_tokens
        state.model = meta.model or state.model
        return result.value, meta.model

    async def _run_tool(
        self, ectx: ExecContext, action: ToolCallAction, summary: str, state: _State
    ) -> Observation:
        try:
            out: ToolOutcome = await self._executor.execute(
                ectx, action.tool, action.arguments, summary=summary
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("executor failed for %s", action.tool)
            await self._bus.emit(
                EventType.SYSTEM_ERROR,
                project_id=ectx.project_id,
                run_id=ectx.run_id,
                agent_id=ectx.agent.id,
                payload={"where": "tool_executor", "tool": action.tool, "error": type(exc).__name__},
            )
            return Observation(
                kind="tool",
                tool=action.tool,
                status="failed",
                text=f"{action.tool} failed unexpectedly.",
                error_code="internal_error",
            )
        refs: list[dict[str, Any]] = []
        if out.status == "ok" and isinstance(out.data, dict) and out.data.get("artifact_id"):
            refs.append(
                {
                    "artifact_id": str(out.data["artifact_id"]),
                    "name": str(out.data.get("name", "")),
                    "version": int(out.data.get("version", 1)),
                }
            )
        obs = Observation(
            kind="tool",
            tool=out.tool,
            status=out.status,
            text=out.text,
            untrusted=out.untrusted,
            source=out.source,
            flags=list(out.flags),
            error_code=out.error_code,
            tool_call_id=out.tool_call_id,
            artifact_refs=refs,
        )
        state.note_artifacts(refs)
        return obs

    # ---- guards ------------------------------------------------------------------------
    def _limit_hit(self, agent: AgentDefinition, state: _State) -> _Stop | None:
        if len(state.records) >= agent.max_steps:
            return _Stop(
                RunStatus.FAILED,
                FailureCategory.TIMEOUT,
                "step_limit",
                f"Stopped after {agent.max_steps} steps without finishing.",
            )
        if state.active_s() >= agent.max_runtime_s:
            return _Stop(
                RunStatus.TIMED_OUT,
                FailureCategory.TIMEOUT,
                "runtime_limit",
                f"Stopped after {agent.max_runtime_s}s of working time.",
            )
        if state.tokens >= agent.token_budget:
            return _Stop(
                RunStatus.FAILED,
                FailureCategory.TIMEOUT,
                "token_budget",
                f"Stopped after using its {agent.token_budget:,}-token budget.",
            )
        return None

    def _after_step(self, agent: AgentDefinition, state: _State, rec: StepRecord) -> _Stop | None:
        """Notes for the next model turn, and the loop breaker."""
        left = agent.max_steps - len(state.records)
        if left == 1 and agent.max_steps > 1:
            rec.notes.append(
                'This is your last step. Finish now with what you have; use status "partial" if anything is incomplete.'
            )
        if agent.max_tool_calls and state.tool_calls == agent.max_tool_calls:
            rec.notes.append("You have used all of your tool calls. Finish now with what you have.")
        if not state.token_warned and state.tokens >= TOKEN_WARN_FRACTION * agent.token_budget:
            state.token_warned = True
            rec.notes.append("You are close to your token budget. Wrap up now.")
        if rec.action_type != "tool_call":
            return None
        window = [_signature(r.action) for r in state.records if r.action_type == "tool_call"][
            -REPEAT_WINDOW:
        ]
        repeats = window.count(_signature(rec.action))
        if repeats >= ABORT_AFTER_REPEATS:
            return _Stop(
                RunStatus.FAILED,
                FailureCategory.MODEL_FAILURE,
                "loop_detected",
                f"Stopped: the same {rec.tool_name} call was repeated {repeats} times without progress.",
            )
        if repeats == NUDGE_AFTER_REPEATS:
            rec.notes.append(
                f"You have made this exact {rec.tool_name} call {repeats} times. Repeating it will not change "
                "the result. Try a different approach, or finish and report what is blocking you."
            )
        return None

    def _wait_hook(self, run_id: str, state: _State) -> Callable[[ApprovalOut | None], Awaitable[None]]:
        async def hook(approval: ApprovalOut | None) -> None:
            if approval is not None:  # parked: waiting for a person does not count as working time
                state.pause()
                await self._runs.set_status(run_id, RunStatus.WAITING_APPROVAL)
            else:
                state.unpause()
                await self._runs.set_status(run_id, RunStatus.RUNNING)

        return hook

    # ---- endings -----------------------------------------------------------------------
    async def _save(self, run_id: str, state: _State) -> None:
        await self._runs.save_progress(
            run_id,
            checkpoint=dump_records(state.records),
            step_count=len(state.records),
            tool_call_count=state.tool_calls,
            tokens_in=state.tokens_in,
            tokens_out=state.tokens_out,
            model=state.model,
        )

    def _reconcile(self, result: TaskResult, state: _State) -> tuple[TaskResult, int]:
        """Only artifacts this run really created may appear in its result."""
        made = state.artifacts
        dropped = sum(1 for a in result.artifacts if a.artifact_id not in made)
        outputs: list[OutputRef] = []
        for o in result.outputs:
            if o.kind == "artifact" and o.artifact_id not in made:
                dropped += 1
                o = o.model_copy(update={"kind": "text", "artifact_id": None})
            outputs.append(o)
        refs = [ArtifactRef(**ref) for ref in made.values()]
        return result.model_copy(update={"artifacts": refs, "outputs": outputs}), dropped

    def _partial(self, state: _State, message: str) -> TaskResult:
        refs = [ArtifactRef(**ref) for ref in state.artifacts.values()]
        return TaskResult(status="failed", summary=f"Stopped: {message}", errors=[message], artifacts=refs)

    async def _finish(self, run_id: str, req: RunRequest, state: _State, result: TaskResult) -> RunOutcome:
        result, dropped = self._reconcile(result, state)
        if dropped:
            log.warning("run %s named %d artifact(s) it did not create; ignored", run_id, dropped)
        payload = result.model_dump(mode="json")
        if result.status == "needs_input":
            await self._runs.set_status(
                run_id, RunStatus.WAITING_INPUT, result={"question": result.summary, "options": []}
            )
            await self._emit(
                EventType.AGENT_MESSAGE, run_id, req, {"kind": "question", "text": result.summary[:500]}
            )
            return RunOutcome(await self._runs.get(run_id), result=result, question=result.summary)
        if result.status == "failed":
            category = _classify_reported_failure(state.records)
            error = {
                "category": category.value,
                "code": "agent_reported_failure",
                "message": result.summary[:500],
                "errors": result.errors[:10],
            }
            run = await self._runs.finish(run_id, RunStatus.FAILED, result=payload, error=error)
            await self._emit(EventType.AGENT_FAILED, run_id, req, {**error, **self._counters(state)})
            return RunOutcome(run, result=result)
        run = await self._runs.finish(run_id, RunStatus.COMPLETED, result=payload)
        await self._emit(
            EventType.AGENT_COMPLETED,
            run_id,
            req,
            {
                "status": result.status,
                "summary": result.summary[:300],
                "artifacts": [a.model_dump() for a in result.artifacts],
                "dropped_artifact_refs": dropped,
                **self._counters(state),
            },
        )
        return RunOutcome(run, result=result)

    async def _ask(
        self, run_id: str, req: RunRequest, state: _State, rec: StepRecord, action: AskHumanAction
    ) -> RunOutcome:
        await self._save(run_id, state)
        await self._runs.set_status(
            run_id,
            RunStatus.WAITING_INPUT,
            result={"question": action.question, "options": action.options},
        )
        await self._emit(
            EventType.AGENT_MESSAGE,
            run_id,
            req,
            {"kind": "question", "text": action.question, "options": action.options},
        )
        return RunOutcome(
            await self._runs.get(run_id), question=action.question, options=list(action.options)
        )

    async def _stop(self, run_id: str, req: RunRequest, state: _State, stop: _Stop) -> RunOutcome:
        await self._save(run_id, state)
        result = self._partial(state, stop.message)
        error = {"category": stop.category.value, "code": stop.code, "message": stop.message}
        run = await self._runs.finish(run_id, stop.status, result=result.model_dump(mode="json"), error=error)
        await self._emit(EventType.AGENT_FAILED, run_id, req, {**error, **self._counters(state)})
        return RunOutcome(run, result=result)

    async def _cancelled(self, run_id: str, req: RunRequest, state: _State) -> None:
        await self._approvals.cancel_for_runs([run_id], "The run was cancelled")
        await self._save(run_id, state)
        result = self._partial(state, "cancelled by the user")
        await self._runs.finish(
            run_id,
            RunStatus.CANCELLED,
            result=result.model_dump(mode="json"),
            error={"code": "cancelled", "message": "Cancelled."},
        )
        await self._emit(EventType.AGENT_CANCELLED, run_id, req, self._counters(state))

    async def _interrupted(self, run_id: str, req: RunRequest, state: _State) -> None:
        """The app is stopping: keep the checkpoint and let the person resume the run later."""
        await self._approvals.cancel_for_runs([run_id], "The app stopped before this was answered")
        await self._save(run_id, state)
        await self._runs.set_status(run_id, RunStatus.INTERRUPTED)
        await self._emit(
            EventType.AGENT_INTERRUPTED, run_id, req, {**self._counters(state), "resumable": True}
        )

    # ---- events ------------------------------------------------------------------------
    @staticmethod
    def _counters(state: _State) -> dict[str, Any]:
        return {
            "steps": len(state.records),
            "tool_calls": state.tool_calls,
            "tokens": state.tokens,
            "model": state.model,
        }

    async def _emit(self, type_: EventType, run_id: str, req: RunRequest, payload: dict[str, Any]) -> None:
        await self._bus.emit(
            type_,
            project_id=req.project_id,
            objective_id=req.objective_id,
            task_id=req.task_id,
            run_id=run_id,
            agent_id=req.agent.id,
            payload=payload,
        )
