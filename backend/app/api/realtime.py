"""Websocket endpoints: arena events (+ personal notifications) and the video STT stream."""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.ratelimit import hit
from backend.app.core.redis import get_redis
from backend.app.core.security import decode_jwt
from backend.app.db.session import session_scope
from backend.app.engine.types import Timing
from backend.app.models import Debate, User
from backend.app.realtime.hub import Connection, hub
from backend.app.realtime.publish import publish_debate
from backend.app.services.debate_view import viewer_counts

router = APIRouter()
log = get_logger("provok.ws")

REACTIONS = {"🔥", "🎯", "🚩", "🤯", "👏", "😂"}
HEARTBEAT_SECONDS = 20
IDLE_TIMEOUT_SECONDS = 90


def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:  # non-browser clients
        return True
    return origin.rstrip("/") in get_settings().cors_origin_list


async def _user_from_ticket(ticket: str | None) -> uuid.UUID | None:
    if not ticket:
        return None
    try:
        return uuid.UUID(decode_jwt(ticket, "ws")["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


async def _publish_viewers(debate_id: uuid.UUID) -> None:
    # At most one viewer-count broadcast per debate every 3s across all instances.
    if await get_redis().set(f"viewers:pub:{debate_id}", "1", nx=True, ex=3):
        count = (await viewer_counts([debate_id])).get(debate_id, 0)
        await publish_debate(debate_id, "viewers", {"count": count})


@router.websocket("/ws/debates/{debate_id}")
async def debate_socket(ws: WebSocket, debate_id: uuid.UUID, ticket: str | None = None) -> None:
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return
    async with session_scope() as db:
        debate = await db.get(Debate, debate_id)
        if debate is None or debate.is_hidden:
            await ws.close(code=4404)
            return
    user_id = await _user_from_ticket(ticket)
    await ws.accept()
    conn = Connection(ws)
    hub.join(conn, f"debate:{debate_id}")
    if user_id:
        hub.join(conn, f"user:{user_id}")
    redis = get_redis()
    presence_key = f"viewers:{debate_id}"
    ip = ws.client.host if ws.client else "unknown"
    sender = asyncio.create_task(conn.sender())
    last_seen = time.monotonic()

    async def heartbeat() -> None:
        while not conn.closed.is_set():
            with contextlib.suppress(Exception):
                await redis.zadd(presence_key, {conn.id: time.time()})
                await redis.expire(presence_key, 600)
            if time.monotonic() - last_seen > IDLE_TIMEOUT_SECONDS:
                conn.closed.set()
                break
            await asyncio.sleep(HEARTBEAT_SECONDS)

    beat = asyncio.create_task(heartbeat())
    await ws.send_text(json.dumps({"type": "hello", "data": {"conn": conn.id, "authenticated": bool(user_id)}}))
    with contextlib.suppress(Exception):
        await _publish_viewers(debate_id)
    try:
        while not conn.closed.is_set():
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=HEARTBEAT_SECONDS * 2)
            except TimeoutError:
                continue
            last_seen = time.monotonic()
            if len(raw) > 1024:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind == "ping":
                conn.offer(json.dumps({"type": "pong", "data": {}}))
            elif kind == "reaction" and msg.get("emoji") in REACTIONS:
                allowed, _ = await hit("ws_react", f"{ip}:{debate_id}", get_settings().rl_ws_reactions)
                if allowed:
                    await publish_debate(debate_id, "reaction", {
                        "emoji": msg["emoji"],
                        "position": msg.get("position") if msg.get("position") in ("for", "against") else None})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        conn.closed.set()
        hub.leave(conn)
        beat.cancel()
        sender.cancel()
        with contextlib.suppress(Exception):
            await redis.zrem(presence_key, conn.id)
            await _publish_viewers(debate_id)


@router.websocket("/ws/debates/{debate_id}/stt")
async def stt_socket(ws: WebSocket, debate_id: uuid.UUID, ticket: str | None = None) -> None:
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return
    user_id = await _user_from_ticket(ticket)
    if user_id is None:
        await ws.close(code=4401)
        return
    async with session_scope() as db:
        debate = await db.get(Debate, debate_id)
        user = await db.get(User, user_id)
        if debate is None or user is None or debate.timing != Timing.VIDEO.value:
            await ws.close(code=4404)
            return
        await db.refresh(debate, ["sides"])
        side = next((s for s in debate.sides if s.user_id == user_id), None)
        if side is None:
            await ws.close(code=4403)
            return
        position = side.position
    await ws.accept()
    from backend.app.video.stt import run_stt_proxy
    await run_stt_proxy(ws, debate_id, user_id, position)
