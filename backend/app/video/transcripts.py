"""
Speech → turns. Finalised STT segments for the active speaker are buffered in
Redis per (debate, round, turn index); when the speaker ends their turn (or the
deadline hits) the buffer becomes a normal turn with source='transcript', and
from there the engine, ledger, judge and voting are identical to text debates.
"""
from __future__ import annotations

import json
import uuid

from backend.app.core.logging import get_logger
from backend.app.core.redis import get_redis
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.engine import transitions as tx
from backend.app.engine.service import TurnPayload, apply_event, get_debate_for_update
from backend.app.engine.types import ModerationStatus, Position, Round, Status, TurnSource
from backend.app.moderation.injection import detect_injection
from backend.app.services.outbox import Outbox
from backend.app.swarm.pipeline import count_words, truncate_words

log = get_logger("provok.transcripts")
BUFFER_TTL = 3 * 3600


def buffer_key(debate_id: uuid.UUID, round_: str, turn_index: int) -> str:
    return f"stt:{debate_id}:{round_}:{turn_index}"


async def append_segment(debate_id: uuid.UUID, round_: str, turn_index: int, text: str, start_ms: int,
                         end_ms: int) -> None:
    key = buffer_key(debate_id, round_, turn_index)
    r = get_redis()
    await r.rpush(key, json.dumps({"text": text, "start_ms": start_ms, "end_ms": end_ms}))
    await r.expire(key, BUFFER_TTL)


async def read_buffer(debate_id: uuid.UUID, round_: str, turn_index: int) -> list[dict]:
    raw = await get_redis().lrange(buffer_key(debate_id, round_, turn_index), 0, -1)
    return [json.loads(x) for x in raw]


async def submit_transcript_if_any(debate_id: uuid.UUID, round_: Round, turn_index: int,
                                   user_id: uuid.UUID | None = None) -> bool:
    """Submit the buffered transcript as the current turn. Returns True if a turn was recorded."""
    segments = await read_buffer(debate_id, round_.value, turn_index)
    text = " ".join(s["text"].strip() for s in segments if s.get("text", "").strip())
    if not text:
        return False
    outbox = Outbox()
    async with session_scope() as db:
        debate = await get_debate_for_update(db, debate_id)
        if not (Status(debate.status).is_round and debate.current_round == round_.value
                and debate.current_turn_index == turn_index):
            return False
        pos, kind = tx.expected_turn(round_, turn_index)
        side = debate.side(pos)
        if user_id is not None and side.user_id != user_id:
            return False
        text = truncate_words(text, debate.word_limit)
        inj = detect_injection(text)
        payload = TurnPayload(
            content=inj.cleaned, word_count=count_words(inj.cleaned), source=TurnSource.TRANSCRIPT,
            injection_flag=inj.flagged, moderation_status=ModerationStatus.UNCHECKED, segments=segments,
            started_ms=segments[0].get("start_ms"), ended_ms=segments[-1].get("end_ms"),
            idempotency_key=f"stt:{round_.value}:{turn_index}",
        )
        try:
            outcome = await apply_event(db, debate, tx.TurnSubmitted(Position(pos), kind, payload.word_count,
                                                                     utcnow()), turn=payload)
        except tx.InvalidTransition as exc:
            log.info("transcript_submit_rejected", code=exc.code)
            return False
        outbox.extend(outcome.outbox)
    await outbox.flush()
    await get_redis().delete(buffer_key(debate_id, round_.value, turn_index))
    return True
