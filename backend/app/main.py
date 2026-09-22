"""
PROVOK — FastAPI Application Entry Point.

Serves both the API (/api/v1/...) and frontend (HTML/CSS/JS) from a single process.
Production-grade with structured logging, security headers, and graceful degradation.
"""
from __future__ import annotations

import uuid
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings, FRONTEND_DIR

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown (with graceful Redis degradation)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application-level startup and shutdown."""
    from backend.app.logging_config import setup_logging, get_logger
    setup_logging()
    logger = get_logger("provok.startup")

    # ── Redis — graceful degradation ──────────────────────────
    try:
        import redis.asyncio as aioredis
        import asyncio
        from backend.app.websockets.manager import manager

        app.state.redis = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        await app.state.redis.ping()  # Verify connection
        logger.info("redis_connected", url=settings.redis_url)

        # Start redis pubsub listener for websockets
        app.state.ws_listener_task = asyncio.create_task(
            manager.start_redis_listener(app.state.redis)
        )
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e),
                       msg="Running without Redis — WebSockets and caching disabled")
        app.state.redis = None
        app.state.ws_listener_task = None

    logger.info("app_started", env=settings.app_env, debug=settings.debug)
    yield

    # ── Shutdown ──────────────────────────────────────────────
    logger = get_logger("provok.shutdown")
    if hasattr(app.state, 'ws_listener_task') and app.state.ws_listener_task:
        app.state.ws_listener_task.cancel()
    if hasattr(app.state, 'redis') and app.state.redis:
        await app.state.redis.close()
    logger.info("app_shutdown")


# ---------------------------------------------------------------------------
# Sentry APM & Error Tracking
# ---------------------------------------------------------------------------

if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
    except Exception:
        pass

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from backend.app.limiter import limiter


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    description="Put your beliefs to the test.",
    version="1.0.0",
    docs_url="/docs" if settings.enable_swagger else None,
    redoc_url="/redoc" if settings.enable_swagger else None,
    lifespan=lifespan,
)

# Attach rate limiter to app state and register exception handler + middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# CORS — configurable origins for production
if settings.debug:
    cors_origins = ["*"]
elif settings.allowed_origins:
    cors_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
else:
    cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_and_tracing(request: Request, call_next):
    """
    Combined middleware:
    1. Attach unique request ID for distributed tracing
    2. Add security headers to every response
    3. Log request timing
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        from backend.app.logging_config import get_logger
        logger = get_logger("provok.http")
        logger.exception("unhandled_exception",
                         path=str(request.url.path),
                         method=request.method,
                         request_id=request_id)
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": request_id},
            status_code=500
        )

    # Timing
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Tracing
    response.headers["X-Request-ID"] = request_id

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

    # Log slow requests in production
    if duration_ms > 1000:
        from backend.app.logging_config import get_logger
        get_logger("provok.http").warning("slow_request",
                                          path=str(request.url.path),
                                          method=request.method,
                                          duration_ms=duration_ms)

    return response


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exception and return clean JSON."""
    from backend.app.logging_config import get_logger
    logger = get_logger("provok.error")
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.exception("unhandled_error",
                     path=str(request.url.path),
                     method=request.method,
                     request_id=request_id,
                     error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred",
            "request_id": request_id,
        }
    )


# ---------------------------------------------------------------------------
# API routers
# ---------------------------------------------------------------------------

from backend.app.api import auth as auth_router
from backend.app.api import users as users_router
from backend.app.api import questions as questions_router
from backend.app.api import debates as debates_router
from backend.app.api import feed as feed_router
from backend.app.api import search as search_router
from backend.app.api import notifications as notifications_router
from backend.app.api import websockets as websockets_router

app.include_router(auth_router.router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
app.include_router(users_router.router, prefix=f"{settings.api_v1_prefix}/users", tags=["users"])
app.include_router(questions_router.router, prefix=f"{settings.api_v1_prefix}/questions", tags=["questions"])
app.include_router(debates_router.router, prefix=f"{settings.api_v1_prefix}/debates", tags=["debates"])
app.include_router(feed_router.router, prefix=f"{settings.api_v1_prefix}", tags=["discovery"])
app.include_router(search_router.router, prefix=f"{settings.api_v1_prefix}/search", tags=["search"])
app.include_router(notifications_router.router, prefix=f"{settings.api_v1_prefix}/notifications", tags=["notifications"])
app.include_router(websockets_router.router, prefix="/ws", tags=["websockets"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check(request: Request):
    """Health check endpoint for load balancers and monitoring."""
    redis_ok = False
    db_ok = False

    # Check Redis
    try:
        if request.app.state.redis:
            await request.app.state.redis.ping()
            redis_ok = True
    except Exception:
        pass

    # Check Database
    try:
        from backend.app.database.core import async_session_factory
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    status_code = 200 if db_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "app": settings.app_name,
            "version": "1.0.0",
            "env": settings.app_env,
            "services": {
                "database": "connected" if db_ok else "disconnected",
                "redis": "connected" if redis_ok else "disconnected",
            }
        }
    )


# ---------------------------------------------------------------------------
# Static files + frontend serving
# ---------------------------------------------------------------------------

# Mount static assets (CSS, JS, images)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# Frontend page routes — serve HTML files
FRONTEND_ROUTES = {
    "/": "index.html",
    "/ask": "ask.html",
    "/live": "live.html",
    "/explore": "explore.html",
    "/search": "search.html",
    "/login": "login.html",
    "/signup": "signup.html",
    "/notifications": "notifications.html",
    "/verdict": "verdict.html",
}


@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend(path: str):
    """
    Catch-all route that serves frontend HTML pages.
    API routes are matched first due to router priority.
    """
    # Normalize path
    route = f"/{path}" if path else "/"

    # Explicitly fail API routes so they don't return HTML
    if route.startswith(settings.api_v1_prefix) or route.startswith("/api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # Direct route match
    if route in FRONTEND_ROUTES:
        html_file = FRONTEND_DIR / FRONTEND_ROUTES[route]
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

    # Favicon
    if route in ["/favicon.ico", "/favicon.png"]:
        from fastapi.responses import FileResponse
        favicon_file = FRONTEND_DIR / route.lstrip("/")
        if favicon_file.exists():
            return FileResponse(favicon_file)
        return HTMLResponse("", status_code=404)

    # Dynamic routes
    if route.startswith("/debate/") and route.endswith("/verdict"):
        html_file = FRONTEND_DIR / "verdict.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

    if route.startswith("/debate/setup/"):
        html_file = FRONTEND_DIR / "debate.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

    if route.startswith("/debate/"):
        html_file = FRONTEND_DIR / "debate.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

    if route.startswith("/profile/"):
        html_file = FRONTEND_DIR / "profile.html"
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

    # Fallback to index
    html_file = FRONTEND_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(html_file.read_text(encoding="utf-8"))

    return HTMLResponse("<h1>404 — Not Found</h1>", status_code=404)
