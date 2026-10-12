"""
Provok API — FastAPI application.

    uvicorn backend.app.main:app            (API + websockets)
    arq backend.app.workers.main.WorkerSettings   (background worker)
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.app.core.config import get_settings
from backend.app.core.errors import install_error_handlers
from backend.app.core.logging import get_logger, setup_logging
from backend.app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from backend.app.core.redis import close_redis, get_redis
from backend.app.db.session import SessionFactory, engine

log = get_logger("provok.app")
VERSION = "2.0.0"


def _init_sentry() -> None:
    s = get_settings()
    if not s.sentry_dsn_api:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    def scrub(event, _hint):  # never ship auth material to Sentry
        req = event.get("request") or {}
        for k in ("cookies", "data"):
            req.pop(k, None)
        headers = req.get("headers") or {}
        for h in list(headers):
            if h.lower() in ("authorization", "cookie", "x-razorpay-signature"):
                headers[h] = "[redacted]"
        return event

    sentry_sdk.init(dsn=s.sentry_dsn_api, environment=s.app_env, release=s.release, send_default_pii=False,
                    traces_sample_rate=s.sentry_traces_sample_rate, before_send=scrub,
                    integrations=[FastApiIntegration(), SqlalchemyIntegration()])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    s = get_settings()
    s.export_provider_keys()
    _init_sentry()
    from backend.app.llm.registry import seed_registry
    from backend.app.realtime.hub import hub
    try:
        async with SessionFactory() as db:
            await seed_registry(db)
            await db.commit()
    except Exception as exc:
        log.error("startup_seed_failed", error=str(exc))
    hub.start()
    worker_task = None
    if s.embedded_worker:
        from arq.worker import create_worker

        from backend.app.workers.main import WorkerSettings
        worker = create_worker(WorkerSettings)
        worker_task = asyncio.create_task(worker.async_run())
        log.info("embedded_worker_started")
    log.info("app_started", env=s.app_env, version=VERSION)
    yield
    await hub.stop()
    if worker_task:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await worker_task
    from backend.app.workers.queue import close_pool
    await close_pool()
    await close_redis()
    await engine.dispose()
    log.info("app_stopped")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Provok API", version=VERSION, lifespan=lifespan,
        docs_url=f"{s.api_prefix}/docs" if s.enable_docs and not s.is_production else None,
        redoc_url=None,
        openapi_url=f"{s.api_prefix}/openapi.json" if s.enable_docs and not s.is_production else None,
    )
    install_error_handlers(app)

    # Middleware (outermost last).
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
                       expose_headers=["X-Request-ID", "Retry-After"], max_age=600)
    app.add_middleware(BodySizeLimitMiddleware)

    from backend.app.api import admin, auth, debates, posts, public, realtime, users, video, wallet
    p = s.api_prefix
    app.include_router(auth.router, prefix=f"{p}/auth", tags=["auth"])
    app.include_router(debates.router, prefix=f"{p}/debates", tags=["debates"])
    app.include_router(users.router, prefix=p, tags=["users"])
    app.include_router(posts.router, prefix=p, tags=["posts"])
    app.include_router(wallet.router, prefix=p, tags=["wallet"])
    app.include_router(public.router, prefix=p, tags=["public"])
    app.include_router(video.router, prefix=p, tags=["video"])
    app.include_router(admin.router, prefix=f"{p}/admin", tags=["admin"])
    app.include_router(realtime.router, tags=["realtime"])

    if s.storage_backend == "local":
        media = Path(s.storage_local_dir)
        media.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=str(media)), name="media")

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    async def assetlinks() -> JSONResponse:
        """Digital Asset Links: lets the Android app (a Trusted Web Activity) show this site without a URL bar."""
        s = get_settings()
        statements = [] if not (s.android_package and s.android_cert_fingerprints) else [{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {"namespace": "android_app", "package_name": s.android_package,
                       "sha256_cert_fingerprints": s.android_cert_fingerprints},
        }]
        return JSONResponse(statements, headers={"Cache-Control": "public, max-age=3600"})

    # HEAD too: uptime monitors and wait-on probe with HEAD, and a 405 reads as "down".
    @app.api_route("/health", methods=["GET", "HEAD"], tags=["ops"])
    async def health() -> dict:
        """Liveness: the process is up."""
        return {"status": "ok", "version": VERSION}

    @app.api_route("/health/ready", methods=["GET", "HEAD"], tags=["ops"])
    async def ready() -> JSONResponse:
        """Readiness: dependencies reachable. Point your uptime monitor here."""
        checks: dict[str, str] = {}
        try:
            async with SessionFactory() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "down"
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
            beat = await get_redis().get("worker:heartbeat")
            if beat:
                age = (datetime.now(datetime.fromisoformat(beat).tzinfo) - datetime.fromisoformat(beat)).total_seconds()
                checks["worker"] = "ok" if age < 120 else "stale"
            else:
                checks["worker"] = "missing"
        except Exception:
            checks["redis"] = "down"
        healthy = checks.get("database") == "ok" and checks.get("redis") == "ok"
        return JSONResponse({"status": "ok" if healthy else "degraded", "checks": checks, "version": VERSION},
                            status_code=200 if healthy else 503)

    return app


app = create_app()
