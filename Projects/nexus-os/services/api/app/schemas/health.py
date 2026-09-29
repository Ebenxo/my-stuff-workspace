"""Health report contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

HealthStatus = Literal["ok", "degraded", "down", "unavailable"]


class HealthCheckResult(BaseModel):
    name: str
    label: str
    status: HealthStatus
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    status: HealthStatus
    version: str
    checks: list[HealthCheckResult]
