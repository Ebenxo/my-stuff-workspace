"""Domain errors. Each carries a stable machine code and an HTTP status for the API layer."""

from __future__ import annotations

from typing import Any


class NexusError(Exception):
    code = "internal_error"
    status_code = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(NexusError):
    code = "not_found"
    status_code = 404


class ConflictError(NexusError):
    code = "conflict"
    status_code = 409


class InvalidRequestError(NexusError):
    code = "invalid_request"
    status_code = 422


class UnauthorizedError(NexusError):
    code = "unauthorized"
    status_code = 401


class ForbiddenError(NexusError):
    code = "forbidden"
    status_code = 403


class RateLimitedError(NexusError):
    code = "rate_limited"
    status_code = 429


class PayloadTooLargeError(NexusError):
    code = "payload_too_large"
    status_code = 413
