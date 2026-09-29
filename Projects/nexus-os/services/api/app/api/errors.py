"""Uniform error envelope: ``{"error": {"code", "message", "details"}}``. No stack traces, no secrets."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import NexusError
from app.providers.errors import BudgetExceededError, NoRouteError, ProviderError

log = logging.getLogger(__name__)


def _envelope(status: int, code: str, message: str, details: object = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NexusError)
    async def _nexus(_: Request, exc: NexusError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(ProviderError)
    async def _provider(_: Request, exc: ProviderError) -> JSONResponse:
        # Messages are already redacted by the adapters; they explain what to fix.
        if isinstance(exc, NoRouteError):
            return _envelope(409, exc.code, exc.message)
        if isinstance(exc, BudgetExceededError):
            return _envelope(429, exc.code, exc.message)
        return _envelope(502, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            {"loc": [str(p) for p in e["loc"]], "message": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        return _envelope(422, "validation_error", "The request was not valid.", {"issues": issues})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return _envelope(500, "internal_error", "Something went wrong. Details are in the local log.")
