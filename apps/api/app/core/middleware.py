"""Security middleware: CSP, CORS, request ID."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline security headers, including a CSP that allows the
    inline styles/scripts our Next.js frontend emits."""

    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", self.CSP)
        return response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and timing."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        dur_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = rid
        response.headers["x-response-time-ms"] = f"{dur_ms:.1f}"
        log.info("http rid=%s %s %s -> %s in %.1fms", rid, request.method, request.url.path, response.status_code, dur_ms)
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection.

    On every response that does not already have a csrf_token cookie,
    we set a fresh cookie. The raw token is also echoed as a response
    header so the SPA can read it and mirror it as X-CSRF-Token on
    unsafe requests.
    """

    SAFE = {"GET", "HEAD", "OPTIONS"}

    def __init__(self, app: ASGIApp, cookie_name: str = "csrf_token", header_name: str = "x-csrf-token") -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        # Validate CSRF BEFORE processing the request on unsafe methods
        if request.method not in self.SAFE:
            cookie = request.cookies.get(self.cookie_name)
            header = request.headers.get(self.header_name)
            if cookie and header and cookie != header:
                from fastapi import HTTPException

                raise HTTPException(403, "CSRF token mismatch")

        response = await call_next(request)

        # Set CSRF cookie if not already present
        if not request.cookies.get(self.cookie_name):
            from app.core.security import new_csrf_token
            raw = new_csrf_token()
            response.set_cookie(
                key=self.cookie_name,
                value=raw,
                httponly=False,
                samesite="lax",
                secure=False,
                max_age=86400,
            )
            response.headers[self.header_name] = raw

        return response
