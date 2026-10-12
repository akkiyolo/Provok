"""
Integration test harness: real Postgres + Redis, fake LLM, inline background jobs.

Env (override in CI):
    TEST_DATABASE_URL  default postgresql://provok@localhost:54329/provok_test
    TEST_REDIS_URL     default redis://localhost:63799/15
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql://provok@localhost:54329/provok_test"),
    "REDIS_URL": os.environ.get("TEST_REDIS_URL", "redis://localhost:63799/15"),
    "JWT_SECRET_KEY": "test-secret-key-that-is-long-enough-1234567890",
    "EMAIL_PROVIDER": "console",
    "CORS_ORIGINS": "http://localhost:3000",
    "WEB_URL": "http://localhost:3000",
    "RAZORPAY_KEY_ID": "rzp_test_key",
    "RAZORPAY_KEY_SECRET": "rzp_test_secret",
    "RAZORPAY_WEBHOOK_SECRET": "whsec_test",
    "TAVILY_API_KEY": "",
    "SEARCH_API_KEY": "",
    "LIVEKIT_URL": "",
    "DEEPGRAM_API_KEY": "",
    "SENTRY_DSN_API": "",
    "LOG_LEVEL": "WARNING",
    "RL_TURN_USER": "1000/60",
    "RL_VOTE_USER": "1000/60",
    "RL_DEBATE_CREATE_USER": "1000/3600",
    "RL_POST_USER": "1000/3600",
    "RL_POST_USER_DAY": "10000/86400",
    "RL_REACTION_USER": "10000/3600",
    "RL_MEDIA_USER": "1000/3600",
    "RL_GENERAL_IP": "100000/60",
    "RL_SIGNUP_IP": "1000/3600",
    "STORAGE_LOCAL_DIR": os.path.join(os.path.dirname(__file__), ".media"),
})

from backend.app.core import config as _config

_config.Settings.model_config["env_file"] = None  # never read the developer's real .env in tests
_config.get_settings.cache_clear()

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text, update  # noqa: E402

from backend.app.core.redis import get_redis  # noqa: E402
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.session import SessionFactory, engine  # noqa: E402
from backend.app.llm import gateway, registry  # noqa: E402
from backend.app.llm.fake import FakeLLM  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.models import ModelRegistry, User  # noqa: E402
from backend.app.services import email as email_svc  # noqa: E402
from backend.app.services import flags  # noqa: E402
from backend.app.workers import queue, tasks  # noqa: E402

ORIGIN = {"Origin": "http://localhost:3000"}


# ── Database lifecycle ─────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean(_schema) -> AsyncIterator[None]:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()
    async with SessionFactory() as db:
        await registry.seed_registry(db)
        await db.execute(update(ModelRegistry).where(ModelRegistry.key != "astra").values(enabled=True))
        await db.commit()
    registry.invalidate_cache()
    flags.invalidate()
    email_svc.sent_emails().clear()
    yield


# ── Fake LLM ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fake_llm() -> AsyncIterator[FakeLLM]:
    fake = FakeLLM()
    gateway.set_test_responder(fake)
    yield fake
    gateway.set_test_responder(None)


# ── Jobs ───────────────────────────────────────────────────────────────────

JOB_FUNCS = {
    "deadline_check": tasks.deadline_check, "swarm_turn": tasks.swarm_turn, "ledger_extract": tasks.ledger_extract,
    "moderate_turn": tasks.moderate_turn, "moderate_post": tasks.moderate_post, "judge_debate": tasks.judge_job, "close_vote": tasks.close_vote_job,
    "video_sync": None, "generate_clips": None,
}


class JobQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple, Any, str | None]] = []
        self.seen_ids: set[str] = set()

    async def __call__(self, name: str, args: tuple, defer_until: Any, job_id: str | None) -> None:
        if job_id and job_id in self.seen_ids:
            return
        if job_id:
            self.seen_ids.add(job_id)
        self.jobs.append((name, args, defer_until, job_id))

    def names(self) -> list[str]:
        return [j[0] for j in self.jobs]

    async def run(self, *, include_deferred: bool = False, max_rounds: int = 200) -> int:
        """Run queued (non-deferred) jobs until the queue drains. Returns jobs executed."""
        executed = 0
        for _ in range(max_rounds):
            runnable = [j for j in self.jobs if include_deferred or j[2] is None]
            if not runnable:
                return executed
            job = runnable[0]
            self.jobs.remove(job)
            fn = JOB_FUNCS.get(job[0])
            if fn is not None:
                await fn({}, *job[1])
                executed += 1
        raise AssertionError("job queue did not drain")


@pytest.fixture(autouse=True)
def jobs() -> AsyncIterator[JobQueue]:
    q = JobQueue()
    queue.set_enqueue_override(q)
    yield q
    queue.set_enqueue_override(None)


# ── HTTP client + user helpers ─────────────────────────────────────────────


@pytest.fixture(scope="session")
async def _app_lifespan() -> AsyncIterator[None]:
    async with app.router.lifespan_context(app):
        yield


@pytest.fixture
async def client(_app_lifespan) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver",
                                 headers=ORIGIN) as c:
        yield c


class Actor:
    def __init__(self, client: httpx.AsyncClient, user: dict, token: str) -> None:
        self.client = client
        self.user = user
        self.token = token

    @property
    def id(self) -> str:
        return self.user["id"]

    @property
    def h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def get(self, path: str, **kw) -> httpx.Response:
        return await self.client.get(path, headers=self.h, **kw)

    async def post(self, path: str, json: Any = None, **kw) -> httpx.Response:
        return await self.client.post(path, json=json, headers=self.h, **kw)


@pytest.fixture
def make_user(client):
    counter = {"n": 0}

    async def _make(username: str | None = None, *, verified: bool = True, credits: int = 0,
                    admin: bool = False, old_account: bool = True) -> Actor:
        counter["n"] += 1
        username = username or f"user{counter['n']}{uuid.uuid4().hex[:4]}"
        r = await client.post("/api/v1/auth/register", json={
            "email": f"{username}@example.com", "password": "correct-horse-battery", "username": username})
        assert r.status_code == 201, r.text
        body = r.json()
        async with SessionFactory() as db:
            values: dict[str, Any] = {"credits": credits}
            if verified:
                values["email_verified_at"] = text("now()")
            if admin:
                values["role"] = "admin"
            if old_account:
                values["created_at"] = text("now() - interval '30 days'")
            await db.execute(update(User).where(User.id == uuid.UUID(body["user"]["id"])).values(**values))
            await db.commit()
        client.cookies.clear()
        return Actor(client, body["user"], body["access_token"])

    return _make
