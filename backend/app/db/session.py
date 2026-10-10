"""Async SQLAlchemy engine + session management."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings

_settings = get_settings()

_connect_args: dict = {
    "server_settings": {
        "statement_timeout": str(_settings.database_statement_timeout_ms),
        "application_name": "provok",
    },
    "command_timeout": 30,
}
if _settings.database_pgbouncer:
    _connect_args["statement_cache_size"] = 0

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args=_connect_args,
    **(
        {"poolclass": NullPool}
        if _settings.is_test
        else {"pool_size": _settings.database_pool_size, "max_overflow": _settings.database_max_overflow}
    ),
)

SessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """For workers/background code: commit on success, roll back on error."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
