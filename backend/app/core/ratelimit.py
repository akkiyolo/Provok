"""Redis sliding-window rate limiter.

Limits are configured as "<count>/<window_seconds>" strings in settings.
If Redis is unreachable the limiter fails open (and logs), so a Redis blip
degrades protection rather than taking the site down.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from fastapi import Request

from backend.app.core.config import get_settings
from backend.app.core.errors import RateLimited
from backend.app.core.logging import get_logger
from backend.app.core.redis import get_redis

log = get_logger("provok.ratelimit")

# KEYS[1]=zset key; ARGV: now_ms, window_ms, limit, member
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = window
  if oldest[2] then retry = (tonumber(oldest[2]) + window) - now end
  return {0, count, retry}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window)
return {1, count + 1, 0}
"""


@dataclass(frozen=True)
class Limit:
    count: int
    window_seconds: int

    @classmethod
    def parse(cls, spec: str) -> Limit:
        count, window = spec.split("/")
        return cls(int(count), int(window))


async def hit(bucket: str, identity: str, spec: str) -> tuple[bool, int]:
    """Record a hit. Returns (allowed, retry_after_seconds)."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return True, 0
    limit = Limit.parse(spec)
    key = f"rl:{bucket}:{identity}"
    now_ms = int(time.time() * 1000)
    try:
        allowed, _count, retry_ms = await get_redis().eval(
            _SLIDING_WINDOW_LUA, 1, key, now_ms, limit.window_seconds * 1000, limit.count,
            f"{now_ms}-{secrets.token_hex(4)}",
        )
    except Exception as exc:  # pragma: no cover - depends on infra failure
        log.warning("ratelimit_redis_unavailable", error=str(exc), bucket=bucket)
        return True, 0
    return bool(allowed), max(1, int(retry_ms) // 1000) if not allowed else 0


async def enforce(bucket: str, identity: str, spec: str, message: str | None = None) -> None:
    allowed, retry_after = await hit(bucket, identity, spec)
    if not allowed:
        raise RateLimited(
            message or "You're doing that too often. Take a breath and try again shortly.",
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


async def reset(bucket: str, identity: str) -> None:
    try:
        await get_redis().delete(f"rl:{bucket}:{identity}")
    except Exception:  # pragma: no cover
        pass


def client_ip(request: Request) -> str:
    """Resolve the client IP, trusting X-Forwarded-For only for configured proxies."""
    hops = get_settings().trusted_proxy_count
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"
