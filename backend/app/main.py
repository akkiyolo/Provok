"""
PROVOK — FastAPI Application Entry Point.

Serves both the API (/api/v1/...) and frontend (HTML/CSS/JS) from a single process.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import get_settings, FRONTEND_DIR

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application-level startup and shutdown."""
    # Startup
    import redis.asyncio as aioredis
    import asyncio
    from backend.app.websockets.manager import manager
    app.state.redis = aioredis.from_url(
        settings.redis_url, decode_responses=True
    )
    
    # Start redis pubsub listener for websockets
    app.state.ws_listener_task = asyncio.create_task(
        manager.start_redis_listener(app.state.redis)
    )
    yield
    # Shutdown
    if hasattr(app.state, 'ws_listener_task'):
        app.state.ws_listener_task.cancel()
    await app.state.redis.close()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    description="Put your beliefs to the test.",
    version="0.1.0",
    docs_url="/docs" if settings.enable_swagger else None,
    redoc_url="/redoc" if settings.enable_swagger else None,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a unique request ID for tracing."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


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
    """Health check endpoint."""
    redis_ok = False
    try:
        await request.app.state.redis.ping()
        redis_ok = True
    except Exception:
        pass

    return JSONResponse({
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "redis": "connected" if redis_ok else "disconnected",
    })


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
}


@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend(path: str):
    """
    Catch-all route that serves frontend HTML pages.
    API routes are matched first due to router priority.
    """
    # Normalize path
    route = f"/{path}" if path else "/"

    # Direct route match
    if route in FRONTEND_ROUTES:
        html_file = FRONTEND_DIR / FRONTEND_ROUTES[route]
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))

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
