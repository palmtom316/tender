"""Global exception handling and request lifecycle middleware."""

from __future__ import annotations

import time

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from tender_backend.core.logging import generate_request_id

logger = structlog.stdlib.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request_id to every request and log request lifecycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_error")
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                },
            )
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            structlog.contextvars.bind_contextvars(
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
            logger.info("request_completed")

        response.headers["X-Request-ID"] = request_id
        return response
