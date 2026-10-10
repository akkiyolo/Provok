"""Debate routes: create, feed, arena state, join/fallback/ready, turns, votes, concede/cancel, verdict."""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.api.deps import DB, ActiveDebater, CurrentUser, OptionalUser, VerifiedUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Conflict, Forbidden, NotFound
from backend.app.core.ratelimit import enforce
from backend.app.core.security import utcnow
from backend.app.engine import transitions as tx
from backend.app.engine.rules import vote_weight
from backend.app.engine.service import TurnPayload, apply_event, get_debate_for_update
from backend.app.engine.types import (
    ROUND_STATUSES,
    ModerationStatus,
    Persona,
    Position,
    Round,
    Status,
    Timing,
    TurnSource,
    UserStatus,
)
from backend.app.models import (
    AnalyticsEvent,
    Claim,
    Clip,
    Debate,
    DebateRound,
    Side,
    Turn,
    User,
    Verdict,
    Vote,
)
from backend.app.moderation.content import check_topic, heuristic_moderation
from backend.app.moderation.injection import detect_injection
from backend.app.services import debates as svc
from backend.app.services.debate_view import build_cards, build_debate_view, public_user
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox
from backend.app.swarm.pipeline import count_words

router = APIRouter()

MAX_TURN_CHARS = 12_000


def _invalid(exc: tx.InvalidTransition) -> AppError:
    return Conflict(exc.message, code=exc.code)


async def _load(db, debate_id: uuid.UUID, viewer: User | None = None) -> Debate:
    debate = await db.get(Debate, debate_id)
    if debate is None or (debate.is_hidden and not (viewer and (viewer.is_admin or debate.created_by == viewer.id))):
        raise NotFound("Debate not found.")
    await db.refresh(debate, ["sides"])
    return debate


# ── Create ─────────────────────────────────────────────────────────────────


class TopicCheckIn(BaseModel):
    question: str = Field(min_length=1, max_length=400)


@router.post("/topic-check")
async def topic_check(body: TopicCheckIn, user: CurrentUser) -> dict:
    await enforce("topic_check", str(user.id), get_settings().rl_topic_check_user)
    r = await check_topic(" ".join(body.question.split()))
    return {"ok": r.ok, "category": r.category, "reason": r.reason, "suggestion": r.suggestion, "code": r.code}


@router.post("", status_code=201)
async def create(body: svc.CreateDebateIn, user: ActiveDebater, db: DB) -> dict:
    created = await svc.create_debate(db, user, body)
    await db.commit()
    await created.outcome.outbox.flush()
    return await build_debate_view(db, created.debate, user)


# ── Feed ───────────────────────────────────────────────────────────────────

FeedTab = Literal["live", "trending", "ava", "challenges", "recent", "completed"]
LIVE_STATUSES = [s.value for s in ROUND_STATUSES] + [Status.LOBBY.value, Status.JUDGING.value]


def _encode_cursor(created_at: datetime, debate_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([created_at.isoformat(), str(debate_id)]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, did = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(ts), uuid.UUID(did)
    except Exception as exc:
        raise AppError("Invalid cursor.", code="bad_cursor") from exc


@router.get("/feed")
async def feed(db: DB, user: OptionalUser, tab: FeedTab = "live", cursor: str | None = None,
               limit: int = Query(default=20, ge=1, le=50), category: str | None = Query(default=None, max_length=40)
               ) -> dict:
    q = select(Debate).where(Debate.is_hidden.is_(False))
    if category:
        q = q.where(Debate.topic_category == category)
    if tab == "trending":
        since = utcnow() - timedelta(days=7)
        votes = select(Vote.debate_id, func.count().label("n")).where(Vote.created_at >= since) \
            .group_by(Vote.debate_id).subquery()
        age_hours = func.extract("epoch", func.now() - Debate.created_at) / 3600.0
        score = (func.coalesce(votes.c.n, 0) * 2 + 1 + func.cast(Debate.is_featured, type_=func.count().type) * 10) \
            / func.power(age_hours + 2, 1.5)
        q = q.outerjoin(votes, votes.c.debate_id == Debate.id).where(
            Debate.created_at >= since, Debate.status.not_in([Status.CANCELLED.value, Status.ABANDONED.value,
                                                              Status.WAITING_FOR_OPPONENT.value]))
        page = int(cursor) if cursor and cursor.isdigit() else 0
        rows = (await db.scalars(q.order_by(desc(score), desc(Debate.created_at)).offset(page * limit)
                                 .limit(limit))).all()
        return {"items": await build_cards(db, list(rows)),
                "next_cursor": str(page + 1) if len(rows) == limit and page < 10 else None}

    if tab == "live":
        q = q.where(Debate.status.in_(LIVE_STATUSES))
    elif tab == "ava":
        q = q.where(Debate.mode == "ava", Debate.status.not_in([Status.CANCELLED.value, Status.ABANDONED.value]))
    elif tab == "challenges":
        open_side = select(Side.debate_id).where(Side.participant_type.is_(None), Side.invited_user_id.is_(None))
        q = q.where(Debate.status.in_([Status.WAITING_FOR_OPPONENT.value, Status.SWARM_FALLBACK_OFFERED.value]),
                    Debate.id.in_(open_side))
    elif tab == "completed":
        q = q.where(Debate.status == Status.COMPLETED.value)
    else:
        q = q.where(Debate.status.not_in([Status.CANCELLED.value, Status.ABANDONED.value]))
    if cursor:
        ts, did = _decode_cursor(cursor)
        q = q.where(or_(Debate.created_at < ts, and_(Debate.created_at == ts, Debate.id < did)))
    order = [desc(Debate.is_featured)] if tab in ("ava", "live") and not cursor else []
    rows = list((await db.scalars(q.order_by(*order, desc(Debate.created_at), desc(Debate.id)).limit(limit))).all())
    cards = await build_cards(db, rows)
    if tab == "live":
        cards.sort(key=lambda c: (not c["is_featured"], -c["viewers"]))
    last = rows[-1] if rows else None
    return {"items": cards, "next_cursor": _encode_cursor(last.created_at, last.id) if last and len(rows) == limit
            else None}


@router.get("/mine")
async def my_debates(user: CurrentUser, db: DB, limit: int = Query(default=30, ge=1, le=50)) -> dict:
    mine = select(Side.debate_id).where(Side.user_id == user.id)
    rows = list((await db.scalars(select(Debate).where(or_(Debate.created_by == user.id, Debate.id.in_(mine)))
                                  .order_by(desc(Debate.created_at)).limit(limit))).all())
    return {"items": await build_cards(db, rows)}


# ── Arena ──────────────────────────────────────────────────────────────────


@router.get("/{debate_id}")
async def get_debate(debate_id: uuid.UUID, db: DB, user: OptionalUser) -> dict:
    debate = await _load(db, debate_id, user)
    return await build_debate_view(db, debate, user)


async def _apply_and_respond(db, debate: Debate, event: tx.Event, user: User | None, **kwargs) -> dict:
    try:
        outcome = await apply_event(db, debate, event, **kwargs)
    except tx.InvalidTransition as exc:
        raise _invalid(exc) from exc
    await db.commit()
    await outcome.outbox.flush()
    return await build_debate_view(db, debate, user)


@router.post("/{debate_id}/join")
async def join(debate_id: uuid.UUID, user: ActiveDebater, db: DB) -> dict:
    debate = await get_debate_for_update(db, debate_id)
    await svc.assert_can_join(db, debate, user)
    view = await _apply_and_respond(db, debate, tx.OpponentJoined(user.id, utcnow()), user)
    if debate.created_by:
        outbox = Outbox()
        await notify(db, outbox, debate.created_by, "opponent_joined",
                     f"{user.display_name} took your challenge", body=debate.question[:200], link=f"/d/{debate.id}")
        await db.commit()
        await outbox.flush()
    return view


class FallbackIn(BaseModel):
    model_key: str | None = Field(default=None, max_length=64)
    persona: Persona | None = None


@router.post("/{debate_id}/fallback")
async def accept_fallback(debate_id: uuid.UUID, body: FallbackIn, user: ActiveDebater, db: DB) -> dict:
    from backend.app.services import flags
    if not await flags.is_enabled(flags.AI_DEBATES):
        raise AppError("AI opponents are paused for a moment.", code="ai_paused", status_code=503)
    model, cfg = await svc.fallback_swarm_config(body.model_key, body.persona)
    locked_user = await db.scalar(select(User).where(User.id == user.id).with_for_update(key_share=True))
    debate = await get_debate_for_update(db, debate_id)
    if debate.created_by != user.id:
        raise Forbidden("Only the creator can bring in an AI opponent.")
    try:
        outcome = await apply_event(db, debate, tx.FallbackAccepted(user.id, utcnow()), swarm_config=cfg)
    except tx.InvalidTransition as exc:
        raise _invalid(exc) from exc
    await svc.charge_ai(db, locked_user, debate, [model])  # raises 402 → whole transaction rolls back
    await db.commit()
    await outcome.outbox.flush()
    return await build_debate_view(db, debate, user)


@router.post("/{debate_id}/ready")
async def ready(debate_id: uuid.UUID, user: ActiveDebater, db: DB) -> dict:
    debate = await get_debate_for_update(db, debate_id)
    return await _apply_and_respond(db, debate, tx.Ready(user.id, utcnow()), user)


class TurnIn(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_TURN_CHARS)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/{debate_id}/turns")
async def submit_turn(debate_id: uuid.UUID, body: TurnIn, user: ActiveDebater, db: DB) -> dict:
    await enforce("turn", str(user.id), get_settings().rl_turn_user)
    if body.idempotency_key:
        existing = await db.scalar(select(Turn.id).where(Turn.debate_id == debate_id,
                                                         Turn.idempotency_key == body.idempotency_key))
        if existing:
            return await build_debate_view(db, await _load(db, debate_id, user), user)

    text = body.content.replace("\r\n", "\n").strip()
    pre = heuristic_moderation(text)
    if "personal_data" in pre.categories:
        raise AppError("Please remove phone numbers or email addresses from your turn.", code="personal_data",
                       status_code=422)
    inj = detect_injection(text)
    content = inj.cleaned.strip()
    words = count_words(content)

    debate = await get_debate_for_update(db, debate_id)
    pos = next((Position(s.position) for s in debate.sides if s.user_id == user.id), None)
    if pos is None:
        raise Forbidden("You're not debating in this one.", code="not_a_debater")
    if debate.current_round is None:
        raise Conflict("No turn is open right now.", code="no_turn_open")
    kind = tx.expected_turn(Round(debate.current_round), debate.current_turn_index)[1]
    payload = TurnPayload(content=content, word_count=words, source=TurnSource.TYPED,
                          idempotency_key=body.idempotency_key, injection_flag=inj.flagged,
                          moderation_status=ModerationStatus.UNCHECKED)
    if inj.flagged:
        locked = await db.scalar(select(User).where(User.id == user.id).with_for_update(key_share=True))
        locked.injection_strikes += 1
        if locked.injection_strikes >= get_settings().injection_strikes_to_restrict:
            locked.status = UserStatus.RESTRICTED.value
    return await _apply_and_respond(db, debate, tx.TurnSubmitted(pos, kind, words, utcnow()), user, turn=payload)


@router.post("/{debate_id}/end-turn")
async def end_video_turn(debate_id: uuid.UUID, user: ActiveDebater, db: DB) -> dict:
    """Video: the speaker finishes early; their buffered transcript becomes the turn."""
    debate = await _load(db, debate_id, user)
    if debate.timing != Timing.VIDEO.value or not debate.current_round:
        raise Conflict("No spoken turn is open.", code="no_turn_open")
    from backend.app.video.transcripts import submit_transcript_if_any
    ok = await submit_transcript_if_any(debate.id, Round(debate.current_round), debate.current_turn_index, user.id)
    if not ok:
        raise Conflict("We didn't catch anything yet. Keep talking, or wait for the timer.", code="empty_transcript")
    await db.refresh(debate)
    return await build_debate_view(db, debate, user)


@router.post("/{debate_id}/concede")
async def concede(debate_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    debate = await get_debate_for_update(db, debate_id)
    return await _apply_and_respond(db, debate, tx.Conceded(user.id, utcnow()), user)


@router.post("/{debate_id}/cancel")
async def cancel(debate_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    debate = await get_debate_for_update(db, debate_id)
    return await _apply_and_respond(db, debate, tx.Cancelled(user.id, utcnow(), is_admin=user.is_admin), user)


# ── Votes ──────────────────────────────────────────────────────────────────


class VoteIn(BaseModel):
    round: Round
    position: Position
    via_share_link: bool = False


@router.post("/{debate_id}/votes")
async def vote(debate_id: uuid.UUID, body: VoteIn, user: VerifiedUser, db: DB) -> dict:
    s = get_settings()
    await enforce("vote", str(user.id), s.rl_vote_user)
    if user.status == UserStatus.BANNED:
        raise Forbidden("This account can't vote.")
    debate = await _load(db, debate_id, user)
    if any(sd.user_id == user.id for sd in debate.sides):
        raise Forbidden("Debaters can't vote in their own debate.", code="debater_cannot_vote")
    row = await db.scalar(select(DebateRound).where(DebateRound.debate_id == debate.id,
                                                    DebateRound.round == body.round.value))
    now = utcnow()
    if row is None or not row.vote_open or (row.vote_closes_at is not None and row.vote_closes_at <= now):
        raise Conflict("Voting for this round isn't open.", code="vote_closed")
    side = debate.side(body.position)
    weight = vote_weight(user.created_at, now, new_account_days=s.new_account_days,
                         new_account_weight=s.new_account_vote_weight)
    stmt = pg_insert(Vote).values(id=uuid.uuid4(), debate_id=debate.id, round=body.round.value, user_id=user.id,
                                  side_id=side.id, weight=weight, via_share_link=body.via_share_link)
    stmt = stmt.on_conflict_do_update(constraint="uq_votes_debate_round_user",
                                      set_={"side_id": side.id, "updated_at": func.now()})
    await db.execute(stmt)
    db.add(AnalyticsEvent(name="vote", user_id=user.id, debate_id=debate.id,
                          props={"round": body.round.value, "via_share_link": body.via_share_link}))
    await db.commit()
    # Tallies stay hidden until the window closes; only a vote count is revealed.
    return {"ok": True, "round": body.round.value, "position": body.position.value}


# ── Verdict ────────────────────────────────────────────────────────────────


@router.get("/{debate_id}/verdict")
async def verdict(debate_id: uuid.UUID, db: DB, user: OptionalUser) -> dict:
    debate = await _load(db, debate_id, user)
    v = await db.scalar(select(Verdict).where(Verdict.debate_id == debate.id))
    if v is None:
        if debate.status == Status.JUDGING.value:
            raise Conflict("The judge is still deliberating.", code="verdict_pending")
        raise NotFound("This debate has no verdict.", code="no_verdict")
    side_pos = {s.id: s.position for s in debate.sides}
    claims = (await db.scalars(select(Claim).where(Claim.debate_id == debate.id).order_by(Claim.seq))).all()
    rounds = (await db.scalars(select(DebateRound).where(DebateRound.debate_id == debate.id))).all()
    clips = (await db.scalars(select(Clip).where(Clip.debate_id == debate.id, Clip.status == "ready"))).all()
    decisive = set(v.decisive_claim_ids or [])
    audience = {r.round: (r.tally if r.vote_closed_at else None) for r in rounds}
    final_round = next((r for r in rounds if r.round == Round.CLOSING.value), None)
    totals = {"for": 0.0, "against": 0.0}
    for t in audience.values():
        if t:
            totals["for"] += float(t.get("for", 0))
            totals["against"] += float(t.get("against", 0))
    audience_winner = None
    if totals["for"] != totals["against"]:
        audience_winner = "for" if totals["for"] > totals["against"] else "against"
    view = await build_debate_view(db, debate, user)
    return {
        "debate": view,
        "judge": {
            "winner_position": side_pos.get(v.winner_side_id) if v.winner_side_id else None,
            "is_close": v.is_close, "scores": v.scores, "per_round": v.per_round, "reasoning": v.reasoning,
            "decisive_claims": [{"id": str(c.id), "seq": c.seq, "position": side_pos.get(c.side_id), "text": c.text,
                                 "status": c.status} for c in claims if str(c.id) in decisive],
            "model_key": v.judge_model_key, "created_at": v.created_at,
        },
        "audience": {"per_round": audience, "totals": totals, "winner_position": audience_winner,
                     "final_vote_open": bool(final_round and final_round.vote_open),
                     "final_vote_closes_at": final_round.vote_closes_at if final_round else None},
        "clips": [{"id": str(c.id), "url": c.url, "reason": c.reason, "caption": c.caption,
                   "duration_ms": c.end_ms - c.start_ms} for c in clips],
    }


@router.get("/{debate_id}/rematch-template")
async def rematch_template(debate_id: uuid.UUID, db: DB, user: CurrentUser) -> dict:
    debate = await _load(db, debate_id, user)
    sides = {s.position: s for s in debate.sides}
    users = {u.id: u for u in (await db.scalars(select(User).where(
        User.id.in_([s.user_id for s in debate.sides if s.user_id])))).all()}

    def spec(side: Side) -> dict:
        if side.user_id == user.id:
            return {"type": "me"}
        if side.user_id:
            return {"type": "invite", "username": users[side.user_id].username}
        if side.swarm_config:
            return {"type": "swarm", **side.swarm_config}
        return {"type": "open"}

    # Swap corners for the rematch.
    return {"question": debate.question, "timing": debate.timing, "word_limit": debate.word_limit,
            "for": spec(sides["against"]), "against": spec(sides["for"]),
            "opponents": [public_user(u) for u in users.values() if u.id != user.id]}
