"""Centralised exception types and handlers. All errors share one JSON envelope:

    {"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("talvynza.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str | None = None, *, code: str | None = None, details: Any = None):
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ")
        if code:
            self.code = code
        self.details = details


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class ValidationFailed(AppError):
    status_code, code = 422, "validation_failed"


class TooManyRequests(AppError):
    status_code, code = 429, "too_many_requests"


def _envelope(request: Request, code: str, message: str, details: Any = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_envelope(request, exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            _envelope(request, "validation_failed", "Request validation failed", details), status_code=422
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Never leak internals to the client.
        log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        return JSONResponse(_envelope(request, "internal_error", "An unexpected error occurred"), status_code=500)
