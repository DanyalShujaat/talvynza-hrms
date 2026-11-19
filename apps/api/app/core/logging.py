"""Structured JSON logging and request-id middleware."""
from __future__ import annotations

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        data.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging(json_logs: bool = True) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if json_logs else logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        logging.getLogger("talvynza.access").info(
            "request",
            extra={"request_id": rid, "method": request.method, "path": request.url.path,
                   "status": response.status_code, "ms": round((time.perf_counter() - start) * 1000, 1)},
        )
        return response
