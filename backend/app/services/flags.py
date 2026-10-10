"""Runtime feature flags / kill switches (DB-backed, briefly cached)."""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import session_scope
from backend.app.models import FeatureFlag

AI_DEBATES = "ai_debates"
VIDEO_DEBATES = "video_debates"
SIGNUPS = "signups"
PAYMENTS = "payments"

DEFAULTS = {AI_DEBATES: True, VIDEO_DEBATES: True, SIGNUPS: True, PAYMENTS: True}
_cache: dict[str, bool] = {}
_cache_at = 0.0


async def is_enabled(key: str) -> bool:
    global _cache, _cache_at
    if time.monotonic() - _cache_at > 15:
        async with session_scope() as db:
            rows = (await db.scalars(select(FeatureFlag))).all()
        _cache = {r.key: r.enabled for r in rows}
        _cache_at = time.monotonic()
    return _cache.get(key, DEFAULTS.get(key, True))


async def set_flag(db: AsyncSession, key: str, enabled: bool, reason: str | None) -> None:
    global _cache_at
    row = await db.get(FeatureFlag, key)
    if row is None:
        db.add(FeatureFlag(key=key, enabled=enabled, reason=reason))
    else:
        row.enabled = enabled
        row.reason = reason
    await db.flush()
    _cache_at = 0.0


def invalidate() -> None:
    global _cache_at
    _cache_at = 0.0
