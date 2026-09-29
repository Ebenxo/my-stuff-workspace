"""Shared enums and base models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PermissionLevel(StrEnum):
    CAUTIOUS = "cautious"
    BALANCED = "balanced"
    PERMISSIVE = "permissive"


class StrictModel(BaseModel):
    """Request models reject unknown fields so typos never silently do nothing."""

    model_config = ConfigDict(extra="forbid")
