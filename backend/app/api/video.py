"""Video routes: role-scoped LiveKit tokens and the LiveKit webhook."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from backend.app.api.deps import DB, OptionalUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, NotFound, PaymentRequired, ServiceUnavailable
from backend.app.core.logging import get_logger
from backend.app.engine.transitions import expected_turn
from backend.app.engine.types import Round, Status, Timing
from backend.app.models import Debate, VideoSession
from backend.app.services import storage
from backend.app.video import livekit as lk

router = APIRouter()
log = get_logger("provok.api.video")


@router.post("/video/{debate_id}/token")
async def video_token(debate_id: uuid.UUID, db: DB, user: OptionalUser) -> dict:
    s = get_settings()
    if not s.livekit_enabled:
        raise ServiceUnavailable("Video isn't available right now.", code="video_unavailable")
    debate = await db.get(Debate, debate_id)
    if debate is None or debate.is_hidden or debate.timing != Timing.VIDEO.value:
        raise NotFound("Video debate not found.")
    status = Status(debate.status)
    if status.is_terminal or status in (Status.WAITING_FOR_OPPONENT, Status.SWARM_FALLBACK_OFFERED):
        raise AppError("This debate isn't on air.", code="not_on_air", status_code=409)
    await db.refresh(debate, ["sides"])
    side = next((sd for sd in debate.sides if user and sd.user_id == user.id), None)
    publisher = side is not None
    speaking = False
    if publisher:
        cap = s.video_free_minutes_per_month
        if cap is not None and lk.minutes_used_this_month(user) >= cap:  # type: ignore[arg-type]
            raise PaymentRequired(f"You've used this month's {cap} free video minutes.", code="video_cap")
        if status is Status.LOBBY:
            speaking = True  # warm-up: both can talk before the bell
        elif status.is_round and debate.current_round:
            pos, _ = expected_turn(Round(debate.current_round), debate.current_turn_index)
            speaking = debate.current_round == Round.CROSS_EXAM.value or pos.value == side.position
    await lk.ensure_session(debate.id)
    return {"token": lk.make_token(debate.id, user=user if publisher else None, speaking=speaking,
                                   publisher=publisher),
            "url": s.livekit_url, "room": lk.room_name(debate.id), "role": "debater" if publisher else "spectator",
            "position": side.position if side else None, "can_speak": speaking}


@router.post("/video/webhook", include_in_schema=False)
async def livekit_webhook(request: Request, db: DB) -> dict:
    s = get_settings()
    if not s.livekit_enabled:
        return {"ok": True}
    from livekit import api
    body = (await request.body()).decode()
    try:
        event = api.WebhookReceiver(api.TokenVerifier(s.livekit_api_key, s.livekit_api_secret)).receive(
            body, request.headers.get("authorization", ""))
    except Exception as exc:
        log.warning("livekit_webhook_rejected", error=str(exc)[:120])
        raise AppError("Invalid webhook.", code="bad_signature", status_code=401) from exc
    if event.event == "egress_ended" and event.egress_info.egress_id:
        vs = await db.scalar(select(VideoSession).where(VideoSession.egress_id == event.egress_info.egress_id))
        if vs is not None and vs.recording_key:
            vs.recording_url = storage.public_url(vs.recording_key)
            await db.commit()
    return {"ok": True}
