"""Provider errors. ``retryable`` drives the gateway's retry/fallback decisions."""

from __future__ import annotations


class ProviderError(Exception):
    code = "provider_error"
    retryable = False

    def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    code = "auth_failed"


class ProviderRateLimited(ProviderError):
    code = "rate_limited"
    retryable = True


class ProviderUnavailable(ProviderError):
    code = "unavailable"
    retryable = True


class ProviderTimeout(ProviderError):
    code = "timeout"
    retryable = True


class ProviderBadRequest(ProviderError):
    code = "bad_request"


class ProviderModelNotFound(ProviderError):
    code = "model_not_found"


class ProviderRefusal(ProviderError):
    code = "refusal"


class InvalidStructuredOutput(ProviderError):
    code = "invalid_output"

    def __init__(self, message: str, *, usage: object | None = None) -> None:
        super().__init__(message)
        # Tokens spent on the failed attempts: the money was spent, so it is still recorded.
        self.usage = usage


class BudgetExceededError(ProviderError):
    """Raised before a call when a hard budget would be exceeded. Never retried or rerouted."""

    code = "budget_exceeded"


class NoRouteError(ProviderError):
    """No configured provider/model can serve the request (e.g. private task with no local model)."""

    code = "no_route"
