"""
LiveKit integration: rooms, role-scoped tokens, server-authoritative speaking
permissions, recording (egress) and minute accounting.

Speaking turns are enforced by permissions, not by asking clients to mute: a
debater whose turn it isn't cannot publish a microphone track at all.
"""
from __future__ import annotations

import math
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.engine.types import Status
from backend.app.models import Debate, User, VideoSession
from backend.app.realtime.publish import publish_debate

log = get_logger("provok.video")


def room_name(debate_id: uuid.UUID) -> str:
    return f"debate-{debate_id}"


def identity_for(user_id: uuid.UUID) -> str:
    return f"u:{user_id}"


def _api():
    from livekit import api
    s = get_settings()
    return api.LiveKitAPI(s.livekit_url, s.livekit_api_key, s.livekit_api_secret)


def _sources(speaking: bool) -> list[int]:
    from livekit.protocol.models import TrackSource
    return [TrackSource.CAMERA, TrackSource.MICROPHONE] if speaking else [TrackSource.CAMERA]


def make_token(debate_id: uuid.UUID, *, user: User | None, speaking: bool, publisher: bool) -> str:
    from livekit import api
    s = get_settings()
    identity = identity_for(user.id) if user else f"s:{secrets.token_hex(6)}"
    grants = api.VideoGrants(
        room_join=True, room=room_name(debate_id), can_subscribe=True, can_publish=publisher,
        can_publish_data=False, hidden=not publisher,
        can_publish_sources=["camera", "microphone"] if (publisher and speaking) else (["camera"] if publisher else []),
    )
    token = (api.AccessToken(s.livekit_api_key, s.livekit_api_secret)
             .with_identity(identity).with_name(user.display_name if user else "Spectator")
             .with_grants(grants).with_ttl(timedelta(hours=3)))
    return token.to_jwt()


async def ensure_session(debate_id: uuid.UUID) -> VideoSession:
    async with session_scope() as db:
        vs = await db.scalar(select(VideoSession).where(VideoSession.debate_id == debate_id))
        if vs is None:
            vs = VideoSession(debate_id=debate_id, livekit_room=room_name(debate_id))
            db.add(vs)
            await db.flush()
    try:
        from livekit import api
        lk = _api()
        try:
            await lk.room.create_room(api.CreateRoomRequest(name=room_name(debate_id), empty_timeout=600,
                                                            max_participants=200))
        finally:
            await lk.aclose()
    except Exception as exc:
        log.warning("livekit_create_room_failed", debate_id=str(debate_id), error=str(exc))
    return vs


async def sync_mute(debate_id: uuid.UUID, speakers: set[str]) -> None:
    """Grant mic only to `speakers` (positions). Also starts/stops recording at the right moments."""
    s = get_settings()
    async with session_scope() as db:
        debate = await db.get(Debate, debate_id)
        if debate is None:
            return
        await db.refresh(debate, ["sides"])
        humans = {sd.position: sd.user_id for sd in debate.sides if sd.user_id}
        status = Status(debate.status)
    await publish_debate(debate_id, "video_turn", {"speakers": sorted(speakers)})
    if not s.livekit_enabled:
        return
    from livekit import api
    from livekit.protocol.models import ParticipantPermission
    lk = _api()
    try:
        for pos, uid in humans.items():
            perm = ParticipantPermission(can_subscribe=True, can_publish=True, can_publish_data=False,
                                         can_publish_sources=_sources(pos in speakers))
            try:
                await lk.room.update_participant(api.UpdateParticipantRequest(
                    room=room_name(debate_id), identity=identity_for(uid), permission=perm))
            except Exception as exc:  # participant may not be connected yet; their token carries the same rule
                log.info("livekit_update_participant_skipped", identity=identity_for(uid), error=str(exc)[:120])
    finally:
        await lk.aclose()
    if status.is_round:
        await start_recording(debate_id)
    elif status in (Status.JUDGING, Status.COMPLETED, Status.ABANDONED, Status.CANCELLED):
        await end_session(debate_id)


async def start_recording(debate_id: uuid.UUID) -> None:
    s = get_settings()
    async with session_scope() as db:
        vs = await db.scalar(select(VideoSession).where(VideoSession.debate_id == debate_id).with_for_update(key_share=True))
        if vs is None or vs.started_at is not None:
            return
        vs.started_at = utcnow()
        if not (s.video_recording_enabled and s.storage_backend == "s3" and s.livekit_enabled):
            return
        from livekit import api
        key = f"recordings/{debate_id}.mp4"
        lk = _api()
        try:
            info = await lk.egress.start_room_composite_egress(api.RoomCompositeEgressRequest(
                room_name=room_name(debate_id), layout="grid",
                file_outputs=[api.EncodedFileOutput(
                    file_type=api.EncodedFileType.MP4, filepath=key,
                    s3=api.S3Upload(access_key=s.s3_access_key_id, secret=s.s3_secret_access_key,
                                    bucket=s.s3_bucket, region=s.s3_region, endpoint=s.s3_endpoint_url or ""))]))
            vs.egress_id = info.egress_id
            vs.recording_key = key
        except Exception as exc:
            log.error("livekit_egress_start_failed", debate_id=str(debate_id), error=str(exc))
        finally:
            await lk.aclose()


async def end_session(debate_id: uuid.UUID) -> None:
    s = get_settings()
    async with session_scope() as db:
        vs = await db.scalar(select(VideoSession).where(VideoSession.debate_id == debate_id).with_for_update(key_share=True))
        if vs is None or vs.ended_at is not None:
            return
        vs.ended_at = utcnow()
        egress_id = vs.egress_id
        if vs.started_at and not vs.minutes_billed:
            minutes = max(1, math.ceil((vs.ended_at - vs.started_at).total_seconds() / 60))
            debate = await db.get(Debate, debate_id)
            await db.refresh(debate, ["sides"])
            period = vs.ended_at.strftime("%Y-%m")
            for side in debate.sides:
                if side.user_id:
                    user = await db.scalar(select(User).where(User.id == side.user_id).with_for_update(key_share=True))
                    if user is None:
                        continue
                    if user.video_minutes_period != period:
                        user.video_minutes_period, user.video_minutes_used_month = period, 0
                    user.video_minutes_used_month += minutes
            vs.minutes_billed = True
    if egress_id and s.livekit_enabled:
        from livekit import api
        lk = _api()
        try:
            await lk.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
        except Exception as exc:
            log.warning("livekit_egress_stop_failed", error=str(exc))
        finally:
            await lk.aclose()


def minutes_used_this_month(user: User) -> int:
    return user.video_minutes_used_month if user.video_minutes_period == utcnow().strftime("%Y-%m") else 0
