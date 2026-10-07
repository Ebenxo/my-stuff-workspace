"""What a run hands back when it finishes.

Ordinary work finishes with a TaskResult. The Planner, Critic and Verifier run in the same loop (with
tools, so they look at real files instead of trusting claims) but finish with their own typed result.
Each kind names a *named* step schema (providers use the name) and tells the model what to return.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.schemas.agents import AgentStep, StepWith, TaskResult
from app.schemas.orchestration import (
    PlanResult,
    PlanStep,
    ReviewResult,
    ReviewStep,
    VerificationResult,
    VerifyStep,
)

TASK_HELP = """\
Finish with {"type": "finish", "result": <TaskResult>}:
{"status": "completed|partial|failed|needs_input", "summary": "what you did and found",
 "outputs": [{"kind": "text|data|artifact", "name": "...", "value": "...", "artifact_id": null}],
 "artifacts": [{"artifact_id": "...", "name": "...", "version": 1}], "errors": [], "recommendations": []}
- Report honestly: "partial" when something is missing, "failed" when you could not do it, with the reason
  in "errors". Never claim work you did not do.
- List an artifact only if you created it with a tool during this run."""

PLAN_HELP = """\
Finish with {"type": "finish", "result": <PlanResult>}:
{"objective": "the objective restated precisely", "assumptions": [], "constraints": [],
 "complexity": "trivial|small|medium|large",
 "tasks": [{"key": "t1", "title": "...", "description": "what to do and what good output looks like",
            "agent": "<slug from the team list>", "depends_on": ["<keys>"], "tools": ["<tool names>"],
            "expected_outputs": ["..."], "approval_required": false, "optional": false, "review": false,
            "complexity": "trivial|small|medium|large"}],
 "risks": [], "required_approvals": [], "completion_criteria": ["checkable statements of done"]}
- Use as few tasks as the objective truly needs; independent tasks must not depend on each other.
- Set "review": true only where a second pair of eyes clearly improves the result (reports, code, copy).
- Completion criteria must be checkable by reading the deliverables."""

REVIEW_HELP = """\
Finish with {"type": "finish", "result": <ReviewResult>}:
{"verdict": "approve|revise", "summary": "your overall judgement",
 "issues": [{"severity": "blocker|major|minor|nit", "category": "correctness|completeness|consistency|
             assumptions|requirements|security|formatting|quality", "location": "file or section",
             "description": "what is wrong", "suggestion": "how to fix it"}],
 "checks": {"correctness": true, "completeness": true, "consistency": true, "assumptions": true,
            "requirements": true, "security": true, "formatting": true, "quality": true}}
- "revise" only for blocker or major issues that the author can fix; otherwise "approve" and list minor issues."""

VERIFY_HELP = """\
Finish with {"type": "finish", "result": <VerificationResult>}:
{"verdict": "PASS|PARTIAL|FAIL", "summary": "what you checked and concluded",
 "criteria": [{"criterion": "...", "met": true, "evidence": "file, section or value you checked"}],
 "missing_requirements": ["what is still missing, specific enough to act on"]}
- PASS only when every criterion is met. PARTIAL when the core is done but something is missing.
  FAIL when the objective is not achieved."""


@dataclass(frozen=True)
class ResultKind:
    name: str
    step: type[StepWith[BaseModel]]
    result: type[BaseModel]
    finish_help: str


KINDS: dict[str, ResultKind] = {
    "task": ResultKind("task", AgentStep, TaskResult, TASK_HELP),  # type: ignore[arg-type]
    "plan": ResultKind("plan", PlanStep, PlanResult, PLAN_HELP),  # type: ignore[arg-type]
    "review": ResultKind("review", ReviewStep, ReviewResult, REVIEW_HELP),  # type: ignore[arg-type]
    "verification": ResultKind("verification", VerifyStep, VerificationResult, VERIFY_HELP),  # type: ignore[arg-type]
}


def kind_of(name: str) -> ResultKind:
    try:
        return KINDS[name]
    except KeyError:
        raise ValueError(f"unknown result kind {name!r}") from None
