"""Publish realtime events (usable from API processes and workers)."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.core.redis import get_redis

log = get_logger("provok.realtime")


def debate_channel(debate_id: uuid.UUID | str) -> str:
    return f"rt:debate:{debate_id}"


def user_channel(user_id: uuid.UUID | str) -> str:
    return f"rt:user:{user_id}"


def _default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    raise TypeError(f"Unserialisable {type(o)}")


async def publish(channel: str, event: str, data: dict[str, Any]) -> None:
    message = json.dumps({"type": event, "data": data, "ts": time.time()}, default=_default, separators=(",", ":"))
    try:
        await get_redis().publish(channel, message)
    except Exception as exc:  # realtime is best-effort; state is always recoverable via REST
        log.warning("realtime_publish_failed", channel=channel, event=event, error=str(exc))


async def publish_debate(debate_id: uuid.UUID | str, event: str, data: dict[str, Any]) -> None:
    await publish(debate_channel(debate_id), event, data)


async def publish_user(user_id: uuid.UUID | str, event: str, data: dict[str, Any]) -> None:
    await publish(user_channel(user_id), event, data)
