"""
ARQ worker entrypoint:   arq backend.app.workers.main.WorkerSettings
"""
from __future__ import annotations

from typing import Any

from arq import cron
from arq.worker import func

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger, setup_logging
from backend.app.core.redis import close_redis
from backend.app.workers import tasks
from backend.app.workers.queue import QUEUE_NAME, redis_settings

log = get_logger("provok.worker")


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    settings = get_settings()
    settings.export_provider_keys()
    if settings.sentry_dsn_api:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn_api, environment=settings.app_env, release=settings.release,
                        traces_sample_rate=settings.sentry_traces_sample_rate)
    log.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_redis()
    log.info("worker_stopped")


_SWEEP_SECONDS = set(range(0, 60, max(1, get_settings().sweeper_interval_seconds)))
_FEATURED_HOURS = {int(h) for h in get_settings().featured_ava_hours_utc.split(",") if h.strip().isdigit()}


class WorkerSettings:
    queue_name = QUEUE_NAME
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 20
    job_timeout = 600
    keep_result = 60
    max_tries = 3
    functions = [
        func(tasks.deadline_check, name="deadline_check", max_tries=3),
        func(tasks.swarm_turn, name="swarm_turn", timeout=420, max_tries=1),
        func(tasks.ledger_extract, name="ledger_extract", max_tries=2),
        func(tasks.moderate_turn, name="moderate_turn", max_tries=2),
        func(tasks.moderate_post, name="moderate_post", max_tries=2),
        func(tasks.factcheck_post, name="factcheck_post", timeout=120, max_tries=1),
        func(tasks.judge_job, name="judge_debate", timeout=900, max_tries=1),
        func(tasks.close_vote_job, name="close_vote"),
        func(tasks.video_sync, name="video_sync", max_tries=2),
        func(tasks.generate_clips, name="generate_clips", timeout=1800, max_tries=1),
    ]
    cron_jobs = [
        cron(tasks.sweeper, second=_SWEEP_SECONDS, run_at_startup=True, unique=True, timeout=55),
        cron(tasks.heartbeat, second={0, 30}, unique=True),
        cron(tasks.spend_check, minute=set(range(0, 60, 10)), second={15}, unique=True),
    ]
    if _FEATURED_HOURS:
        cron_jobs.append(cron(tasks.featured_job, hour=_FEATURED_HOURS, minute={0}, second={30}, unique=True,
                              timeout=120))
