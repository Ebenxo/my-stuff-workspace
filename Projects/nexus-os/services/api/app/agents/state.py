"""The checkpoint: everything an agent run needs to be resumed, and nothing it should not keep.

A step records the agent's public summary, the action it proposed and what came back. It never holds
hidden reasoning (providers discard thinking blocks), so a checkpoint is safe to store and show.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    kind: Literal["tool", "human", "system"] = "tool"
    tool: str | None = None
    status: str = "ok"  # ok | denied | failed | invalid | interrupted | answered | refused
    text: str = ""
    untrusted: bool = False
    source: str | None = None
    flags: list[str] = Field(default_factory=list)
    error_code: str | None = None
    tool_call_id: str | None = None
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)  # artifacts this tool call saved


class StepRecord(BaseModel):
    n: int
    summary: str
    action: dict[str, Any]
    observation: Observation | None = None  # None while the action is still in flight
    notes: list[str] = Field(default_factory=list)  # runner guidance shown after the observation
    model: str | None = None

    @property
    def action_type(self) -> str:
        return str(self.action.get("type", ""))

    @property
    def tool_name(self) -> str | None:
        return str(self.action["tool"]) if self.action_type == "tool_call" else None


def dump_records(records: list[StepRecord]) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in records]


def load_records(raw: list[dict[str, Any]]) -> list[StepRecord]:
    return [StepRecord.model_validate(r) for r in raw]
