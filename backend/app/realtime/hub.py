"""
Websocket hub (one per API process).

A single Redis pattern subscription fans events out to local sockets. Each socket
has a bounded send queue; a client that can't keep up is disconnected rather than
slowing down the room. Clients always re-sync via REST on (re)connect, so a
dropped event is never fatal.
"""
from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections import defaultdict

from fastapi import WebSocket

from backend.app.core.logging import get_logger
from backend.app.core.redis import get_redis

log = get_logger("provok.hub")
QUEUE_SIZE = 256


class Connection:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.id = secrets.token_hex(8)
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.closed = asyncio.Event()

    def offer(self, message: str) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            log.info("ws_slow_consumer_dropped", conn=self.id)
            self.closed.set()

    async def sender(self) -> None:
        try:
            while not self.closed.is_set():
                getter = asyncio.create_task(self.queue.get())
                closer = asyncio.create_task(self.closed.wait())
                done, pending = await asyncio.wait({getter, closer}, return_when=asyncio.FIRST_COMPLETED)
                for p in pending:
                    p.cancel()
                if getter in done:
                    await self.ws.send_text(getter.result())
        except Exception:
            self.closed.set()


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, set[Connection]] = defaultdict(set)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._listen_forever())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    def join(self, conn: Connection, channel: str) -> None:
        self.rooms[channel].add(conn)

    def leave(self, conn: Connection) -> None:
        for channel in [c for c, conns in self.rooms.items() if conn in conns]:
            self.rooms[channel].discard(conn)
            if not self.rooms[channel]:
                del self.rooms[channel]

    async def _listen_forever(self) -> None:
        backoff = 1.0
        while True:
            pubsub = get_redis().pubsub()
            try:
                await pubsub.psubscribe("rt:*")
                log.info("hub_subscribed")
                backoff = 1.0
                async for msg in pubsub.listen():
                    if msg.get("type") != "pmessage":
                        continue
                    channel = str(msg["channel"])[3:]  # strip "rt:"
                    for conn in list(self.rooms.get(channel, ())):
                        conn.offer(msg["data"])
            except asyncio.CancelledError:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                raise
            except Exception as exc:
                log.warning("hub_listener_error", error=str(exc), retry_in=backoff)
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)


hub = Hub()
