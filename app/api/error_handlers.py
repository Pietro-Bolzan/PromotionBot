"""How every failure becomes the same JSON error body."""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import AppError
from app.core.request_context import request_id_var
from app.core.security import describe_error

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
}


def error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: list | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict = {
        "error_code": error_code,
        "message": message,
        "request_id": request_id_var.get(),
    }
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def _app_error(request: Request, error: AppError) -> JSONResponse:
    return error_response(error.status_code, error.error_code, str(error))


async def _http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    return error_response(
        error.status_code,
        _HTTP_ERROR_CODES.get(error.status_code, "http_error"),
        str(error.detail),
        headers=error.headers,
    )


async def _validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    return error_response(
        422,
        "validation_error",
        "The request is invalid",
        details=jsonable_encoder(error.errors()),
    )


async def _upstream_error(request: Request, error: httpx.HTTPError) -> JSONResponse:
    # Network failures talking to Telegram: the promotion was already recorded
    # as a failed attempt, so this only tells the caller what happened.
    logger.warning("External service unreachable: %s", describe_error(error))
    return error_response(
        502, "upstream_unreachable", "An external service could not be reached"
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(httpx.HTTPError, _upstream_error)


class UnhandledErrorMiddleware:
    """Last line of defense: an unexpected exception becomes a standard 500.

    Starlette's own handler for Exception runs outside every app middleware,
    where the request id is already gone. Sitting inside RequestIdMiddleware,
    this one logs the failure with the request's id and answers with it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            if response_started:
                raise  # too late for another response; the server closes it
            response = error_response(500, "internal_error", "Internal server error")
            await response(scope, receive, send)
