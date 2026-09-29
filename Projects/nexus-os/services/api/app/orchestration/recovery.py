"""Deterministic recovery decisions for a failed task. Pure: facts in, decision out.

The model is never asked how to recover: the same failure always gets the same response, every
decision is recorded as an event with its reason, and each row of the table is unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.failures import FailureCategory

Action = Literal["retry", "resume", "skip", "block", "fail"]

# Codes the runner uses when it stops a run that could continue from its checkpoint.
RESUMABLE_CODES = frozenset({"step_limit", "tool_call_limit", "runtime_limit", "token_budget", "interrupted"})
# Provider error codes (app/providers/errors.py) that no retry can fix.
PERMANENT_MODEL_CODES = frozenset(
    {"budget_exceeded", "no_route", "refusal", "auth_failed", "model_not_found", "bad_request"}
)


@dataclass(frozen=True)
class Failure:
    category: FailureCategory
    code: str
    message: str
    attempts: int  # attempts already made, including the one that just failed
    max_attempts: int
    optional: bool


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str

    @property
    def needs_person(self) -> bool:
        return self.action == "block"


def _give_up(f: Failure, why: str) -> Decision:
    if f.optional:
        return Decision("skip", f"{why} The task is optional, so it is skipped and the rest continue.")
    return Decision("block", f"{why} It needs your decision: retry it, or skip it.")


def decide(f: Failure) -> Decision:
    left = f.attempts < f.max_attempts

    if f.category is FailureCategory.PERMISSION_DENIED:
        # A person (or the policy) said no. Retrying the same thing would just ask again.
        return _give_up(f, "An action it needed was not allowed.")

    if f.code == "agent_reported_failure":
        # The agent itself says it cannot do this; a blind retry is likely to fail the same way.
        return _give_up(f, "The agent reported it could not complete the task.")

    if f.category is FailureCategory.TIMEOUT or f.code in RESUMABLE_CODES:
        if left and f.code in RESUMABLE_CODES:
            return Decision("resume", f"Stopped at a limit ({f.code}); continuing from its last step.")
        return _give_up(f, "It ran out of room again after continuing.")

    if f.code == "loop_detected":
        if left:
            return Decision("retry", "It kept repeating the same action; starting the task fresh.")
        return _give_up(f, "It kept repeating itself.")

    if f.category in (FailureCategory.MODEL_FAILURE, FailureCategory.INVALID_OUTPUT):
        if f.code in PERMANENT_MODEL_CODES:
            # Retrying cannot fix a budget stop, a missing model or key, a bad request or a refusal.
            return _give_up(f, f"The model could not be used ({f.code}).")
        if left:
            return Decision(
                "retry", "The model call failed after its own retries and fallbacks; trying again."
            )
        return _give_up(f, "The model kept failing.")

    if f.category is FailureCategory.TOOL_FAILURE:
        if left:
            return Decision(
                "retry", "A tool failed; trying the task again so the agent can take another route."
            )
        return _give_up(f, "Its tools kept failing.")

    if left:
        return Decision("retry", "Unexpected failure; trying once more.")
    return _give_up(f, "It failed again.")
