"""Request id: one identifier shared by every log line of a request or cycle."""

import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "x-request-id"

# Accepted from the client only in this shape, so the header cannot inject
# arbitrary text into the logs.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def new_request_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex}"


class RequestIdMiddleware:
    """Give every HTTP request an id, readable by every log line it produces.

    The id comes from the X-Request-ID header when a caller (a proxy, say)
    already set a valid one, and is returned in that header either way.

    A plain ASGI middleware rather than Starlette's BaseHTTPMiddleware: uvicorn
    writes its access log from inside `send`, so the id must still be set when
    the response goes out.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.encode())
        request_id = incoming.decode("latin-1") if incoming else ""
        if not _VALID_REQUEST_ID.fullmatch(request_id):
            request_id = new_request_id()

        # Also on request.state, for code that runs outside this context.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [*message.get("headers", [])]
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
