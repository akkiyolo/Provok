"""
Streaming speech-to-text proxy (Deepgram behind an interface).

The debater's browser streams its own microphone (MediaRecorder/webm-opus) to
our websocket. We forward audio to the STT provider only while the server says
that debater may speak, publish live captions to the arena, and buffer final
segments for the turn. The provider key never reaches the browser.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from fastapi import WebSocket

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.engine.transitions import expected_turn
from backend.app.engine.types import Round, Status
from backend.app.models import Debate, VideoSession
from backend.app.realtime.publish import publish_debate
from backend.app.video.transcripts import append_segment

log = get_logger("provok.stt")


class STTStream(Protocol):
    async def send(self, chunk: bytes) -> None: ...
    def results(self) -> AsyncIterator[dict]: ...
    async def close(self) -> None: ...


class DeepgramStream:
    def __init__(self, ws) -> None:
        self.ws = ws

    @classmethod
    async def open(cls) -> DeepgramStream:
        from websockets.asyncio.client import connect
        s = get_settings()
        url = (f"wss://api.deepgram.com/v1/listen?model={s.deepgram_model}&smart_format=true&punctuate=true"
               "&interim_results=true&endpointing=300")
        ws = await connect(url, additional_headers={"Authorization": f"Token {s.deepgram_api_key}"},
                           open_timeout=10, max_size=2**20)
        return cls(ws)

    async def send(self, chunk: bytes) -> None:
        await self.ws.send(chunk)

    async def results(self) -> AsyncIterator[dict]:
        async for message in self.ws:
            try:
                data = json.loads(message)
            except (TypeError, json.JSONDecodeError):
                continue
            if data.get("type") != "Results":
                continue
            alt = (data.get("channel", {}).get("alternatives") or [{}])[0]
            text = (alt.get("transcript") or "").strip()
            if not text:
                continue
            start = float(data.get("start", 0))
            dur = float(data.get("duration", 0))
            yield {"text": text, "is_final": bool(data.get("is_final")),
                   "start_ms": int(start * 1000), "end_ms": int((start + dur) * 1000)}

    async def close(self) -> None:
        try:
            await self.ws.send(json.dumps({"type": "CloseStream"}))
            await self.ws.close()
        except Exception:
            pass


async def _speaker_state(debate_id: uuid.UUID, user_id: uuid.UUID) -> tuple[str, int, str] | None:
    """(round, turn_index, position) if this user may speak right now, else None."""
    async with session_scope() as db:
        d = await db.get(Debate, debate_id)
        if d is None or not Status(d.status).is_round or not d.current_round:
            return None
        await db.refresh(d, ["sides"])
        mine = next((s for s in d.sides if s.user_id == user_id), None)
        if mine is None:
            return None
        pos, _ = expected_turn(Round(d.current_round), d.current_turn_index)
        if pos.value == mine.position or d.current_round == Round.CROSS_EXAM.value:
            return d.current_round, d.current_turn_index, mine.position
        return None


async def run_stt_proxy(ws: WebSocket, debate_id: uuid.UUID, user_id: uuid.UUID, position: str) -> None:
    s = get_settings()
    if not s.deepgram_api_key:
        await ws.close(code=4503, reason="Transcription unavailable")
        return
    try:
        stream = await DeepgramStream.open()
    except Exception as exc:
        log.error("deepgram_connect_failed", error=str(exc))
        await ws.close(code=4503, reason="Transcription unavailable")
        return

    state: dict[str, tuple[str, int, str] | None] = {"speaker": None}
    async with session_scope() as db:
        from sqlalchemy import select
        vs = await db.scalar(select(VideoSession).where(VideoSession.debate_id == debate_id))
        recording_start = vs.started_at if vs else None

    def recording_ms() -> int:
        """Wall-clock offset into the recording (STT timestamps drift because we gate audio by turn)."""
        if recording_start is None:
            return 0
        return max(0, int((utcnow() - recording_start).total_seconds() * 1000))

    async def refresh_state() -> None:
        while True:
            state["speaker"] = await _speaker_state(debate_id, user_id)
            await asyncio.sleep(1.0)

    async def pump_results() -> None:
        async for r in stream.results():
            sp = state["speaker"]
            await publish_debate(debate_id, "caption", {"position": position, "text": r["text"],
                                                        "final": r["is_final"]})
            if r["is_final"] and sp is not None:
                round_, idx, _pos = sp
                expected_pos = expected_turn(Round(round_), idx)[0].value
                if expected_pos == position:  # only the active speaker's words become the turn
                    end = recording_ms()
                    await append_segment(debate_id, round_, idx, r["text"],
                                         max(0, end - (r["end_ms"] - r["start_ms"])), end)

    refresher = asyncio.create_task(refresh_state())
    pump = asyncio.create_task(pump_results())
    bytes_in = 0
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            chunk = msg.get("bytes")
            if not chunk:
                continue
            bytes_in += len(chunk)
            if bytes_in > 200 * 1024 * 1024:  # hard cap per connection
                break
            if state["speaker"] is not None:
                await stream.send(chunk)
    except Exception as exc:
        log.info("stt_client_closed", error=str(exc)[:120])
    finally:
        refresher.cancel()
        pump.cancel()
        await stream.close()
