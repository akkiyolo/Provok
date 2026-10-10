"""ASGI middleware: request ids + access logs, security headers, body-size limit, global IP rate limit."""
from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.ratelimit import client_ip, hit

log = get_logger("provok.http")

_UNLIMITED_PATHS = ("/health", "/api/v1/payments/webhook", "/api/v1/video/webhook")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id")
        if not rid or len(rid) > 64 or not rid.replace("-", "").isalnum():
            rid = uuid.uuid4().hex
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        settings = get_settings()
        path = request.url.path

        if settings.rate_limit_enabled and not path.startswith(_UNLIMITED_PATHS):
            allowed, retry = await hit("global", client_ip(request), settings.rl_general_ip)
            if not allowed:
                return JSONResponse({"error": {"code": "rate_limited", "message": "Slow down a little.",
                                               "details": {"retry_after": retry}}, "request_id": rid},
                                    status_code=429, headers={"Retry-After": str(retry), "X-Request-ID": rid})

        start = time.perf_counter()
        response = await call_next(request)
        ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        _security_headers(response, settings.is_production)
        if path.startswith(settings.api_prefix) and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        level = "warning" if ms > 1500 or response.status_code >= 500 else "info"
        getattr(log, level)("request", method=request.method, path=path, status=response.status_code, ms=ms,
                            user_id=getattr(request.state, "user_id", None))
        return response


def _security_headers(response: Response, production: bool) -> None:
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cross-Origin-Resource-Policy", "same-site")
    # The API only serves JSON; nothing it returns should ever execute.
    h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    if production:
        h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")


class BodySizeLimitMiddleware:
    """Reject request bodies over the limit without buffering them (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        s = get_settings()
        limit = s.max_upload_bytes + 64_000 if scope["path"].endswith("/avatar") else s.max_request_body_bytes
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _too_large(send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send: Send) -> None:
    resp = JSONResponse({"error": {"code": "payload_too_large", "message": "Request is too large."}}, status_code=413)
    await resp({"type": "http"}, None, send)  # type: ignore[arg-type]
