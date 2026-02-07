"""Middleware: session cookies, rate limiting, file validation per T009a/T012."""

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.src.api.schemas import RATE_LIMITED, UNAUTHORIZED, make_error
import backend.src.config as _config

COOKIE_NAME = "session_token"

# Paths that don't require a session cookie
_PUBLIC_PATHS = frozenset({
    "/api/v1/sessions",
    "/api/v1/fork/upload",
    "/api/v1/fork/configure",
    "/api/v1/fork/geometry",
    "/api/v1/fork/stl",
})


class SessionCookieMiddleware(BaseHTTPMiddleware):
    """Validate session cookie on all protected routes."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Public paths: session creation and fork calibration endpoints
        if path in _PUBLIC_PATHS:
            return await call_next(request)

        # All other /api routes require a valid session cookie
        if path.startswith("/api/"):
            token = request.cookies.get(COOKIE_NAME)
            if not token:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=401,
                    content=make_error(
                        UNAUTHORIZED,
                        "Session cookie required",
                    ),
                )
            # Store token on request state for route handlers
            request.state.session_token = token

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP sliding window rate limiter."""

    def __init__(self, app: object) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._requests: dict[str, list[float]] = {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = 60.0

        timestamps = self._requests.get(client_ip, [])
        timestamps = [t for t in timestamps if now - t < window]
        timestamps.append(now)
        self._requests[client_ip] = timestamps

        if len(timestamps) > _config.RATE_LIMIT_PER_MINUTE:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content=make_error(
                    RATE_LIMITED,
                    "Too many requests",
                    limit=_config.RATE_LIMIT_PER_MINUTE,
                ),
            )

        return await call_next(request)


# File validation helpers (used by route handlers, not middleware)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SCAN_TYPES = {"application/octet-stream"}  # STL files


def validate_image_file(content_type: str, size: int) -> str | None:
    """Returns error message if invalid, None if OK."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        return f"File must be JPEG, PNG, or WebP format. Received: {content_type}"
    if size > _config.MAX_IMAGE_SIZE_BYTES:
        return f"File exceeds {_config.MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB limit"
    return None


def validate_scan_file(size: int) -> str | None:
    """Returns error message if invalid, None if OK."""
    if size > _config.MAX_STL_SIZE_BYTES:
        return f"File exceeds {_config.MAX_STL_SIZE_BYTES // (1024 * 1024)} MB limit"
    return None
