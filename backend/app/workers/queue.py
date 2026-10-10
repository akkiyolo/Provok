"""Job enqueueing (ARQ). Job ids are deterministic so duplicate enqueues are no-ops."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

log = get_logger("provok.queue")

QUEUE_NAME = "provok:jobs"

_pool: ArqRedis | None = None
EnqueueFn = Callable[[str, tuple[Any, ...], datetime | None, str | None], Awaitable[None]]
_override: EnqueueFn | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


def set_enqueue_override(fn: EnqueueFn | None) -> None:
    """Tests capture jobs instead of sending them to Redis."""
    global _override
    _override = fn


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings(), default_queue_name=QUEUE_NAME)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue(name: str, *args: Any, defer_until: datetime | None = None, job_id: str | None = None) -> None:
    if _override is not None:
        await _override(name, args, defer_until, job_id)
        return
    try:
        pool = await get_pool()
        await pool.enqueue_job(name, *args, _job_id=job_id, _defer_until=defer_until, _queue_name=QUEUE_NAME)
    except Exception as exc:
        # The sweeper recovers anything time-based from DB state; log loudly but don't fail the request.
        log.error("enqueue_failed", job=name, job_id=job_id, error=str(exc))
