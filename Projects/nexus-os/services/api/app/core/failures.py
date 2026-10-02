"""Failure categories shared by the provider gateway, agent runner and orchestrator."""

from __future__ import annotations

from enum import StrEnum


class FailureCategory(StrEnum):
    MODEL_FAILURE = "MODEL_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    CONTEXT_FAILURE = "CONTEXT_FAILURE"
    UNKNOWN = "UNKNOWN"
