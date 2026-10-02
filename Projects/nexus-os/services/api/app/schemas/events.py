"""Event contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventRecord(BaseModel):
    """One immutable entry of the audit trail."""

    model_config = ConfigDict(frozen=True)

    seq: int
    id: str
    ts: datetime
    type: str
    project_id: str | None = None
    objective_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None
    actor: str = "system"
    payload: dict[str, Any] = {}
    prev_hash: str
    hash: str


class ChainVerification(BaseModel):
    ok: bool
    chains_checked: int
    events_checked: int
    first_bad_seq: int | None = None
    detail: str | None = None
