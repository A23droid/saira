"""
Global exception handlers.

Registered once in `app.main`. Keeps every error response in the same
shape — `{"detail": "..."}` — regardless of whether it came from a domain
`AppError`, a Pydantic validation failure, or an unexpected exception.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions import AppError

logger = logging.getLogger("saira.errors")


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    """Pydantic v2 embeds the raw exception object (e.g. a `ValueError`) in
    `ctx.error` for errors raised from a custom `field_validator`. That
    object isn't JSON-serializable, so we stringify it before it ever
    reaches `JSONResponse`."""
    sanitized = []
    for error in errors:
        error = dict(error)
        ctx = error.get("ctx")
        if isinstance(ctx, dict) and "error" in ctx:
            ctx = dict(ctx)
            ctx["error"] = str(ctx["error"])
            error["ctx"] = ctx
        sanitized.append(error)
    return sanitized


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error.",
                "errors": _sanitize_validation_errors(exc.errors()),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the real error server-side; never leak internals to the client.
        logger.exception("Unhandled exception while processing %s %s", request.method, request.url)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
