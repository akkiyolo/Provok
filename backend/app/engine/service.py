"""
Engine service: the only code that changes a debate's state.

    async with debate_lock(db, debate_id) as debate:
        outcome = await apply_event(db, debate, event, ...)
    await db.commit(); await outcome.outbox.flush()

`apply_event` runs the pure transition, persists the new state and DB-side effects
in the caller's transaction, and queues post-commit effects (jobs, realtime) in an
Outbox that the caller flushes after committing.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import Conflict, NotFound
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.engine import transitions as tx
from backend.app.engine.config import engine_config
from backend.app.engine.rules import tally
from backend.app.engine.types import (
    Mode,
    ModerationStatus,
    ParticipantType,
    Position,
    Round,
    Status,
    Timing,
    TurnSource,
)
from backend.app.models import AuditLog, Debate, DebateRound, Side, Turn, User, Vote
from backend.app.payments.credits import refund_debate
from backend.app.realtime.publish import publish_debate
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox
from backend.app.workers.queue import enqueue

log = get_logger("provok.engine")

FORFEIT_TEXT = "No response."


@dataclass
class TurnPayload:
    content: str
    word_count: int
    source: TurnSource
    model_key: str | None = None
    idempotency_key: str | None = None
    injection_flag: bool = False
    moderation_status: ModerationStatus = ModerationStatus.UNCHECKED
    citations: list[dict[str, Any]] | None = None
    segments: list[dict[str, Any]] | None = None
    started_ms: int | None = None
    ended_ms: int | None = None


@dataclass
class Outcome:
    transition: tx.Transition
    outbox: Outbox = field(default_factory=Outbox)
    recorded_turns: list[Turn] = field(default_factory=list)


# ── Loading ────────────────────────────────────────────────────────────────


async def get_debate_for_update(db: AsyncSession, debate_id: uuid.UUID, *, skip_locked: bool = False) -> Debate:
    stmt = select(Debate).where(Debate.id == debate_id).with_for_update(key_share=True, skip_locked=skip_locked)
    debate = await db.scalar(stmt)
    if debate is None:
        raise NotFound("Debate not found.")
    await db.refresh(debate, ["sides"])
    return debate


def to_state(debate: Debate) -> tx.DebateState:
    sides = {}
    for s in debate.sides:
        pos = Position(s.position)
        sides[pos] = tx.SideState(
            position=pos,
            participant_type=ParticipantType(s.participant_type) if s.participant_type else None,
            user_id=s.user_id,
            invited_user_id=s.invited_user_id,
            ready=s.ready_at is not None,
        )
    return tx.DebateState(
        status=Status(debate.status), mode=Mode(debate.mode), timing=Timing(debate.timing),
        created_by=debate.created_by, sides=sides, word_limit=debate.word_limit,
        current_round=Round(debate.current_round) if debate.current_round else None,
        turn_index=debate.current_turn_index, deadline_at=debate.deadline_at,
        swarm_retry_count=debate.swarm_retry_count,
        paused_from=Status(debate.paused_from) if debate.paused_from else None,
        paused_reason=debate.paused_reason,
        conceded_position=Position(debate.conceded_position) if debate.conceded_position else None,
    )


def _persist_state(debate: Debate, st: tx.DebateState) -> None:
    debate.status = st.status.value
    debate.mode = st.mode.value
    debate.timing = st.timing.value
    debate.current_round = st.current_round.value if st.current_round else None
    debate.current_turn_index = st.turn_index
    debate.deadline_at = st.deadline_at
    debate.swarm_retry_count = st.swarm_retry_count
    debate.paused_from = st.paused_from.value if st.paused_from else None
    debate.paused_reason = st.paused_reason
    debate.conceded_position = st.conceded_position.value if st.conceded_position else None


# ── Applying events ────────────────────────────────────────────────────────


async def apply_event(db: AsyncSession, debate: Debate, event: tx.Event, *, turn: TurnPayload | None = None,
                      swarm_config: dict[str, Any] | None = None) -> Outcome:
    """Apply `event` to a row-locked debate. Raises tx.InvalidTransition on illegal events."""
    cfg = engine_config(debate.timing)
    t = tx.transition(to_state(debate), event, cfg)
    outcome = Outcome(t)
    _persist_state(debate, t.state)
    await _apply_db_effects(db, debate, t, outcome, turn=turn, swarm_config=swarm_config, now=_event_time(event))
    await db.flush()
    _queue_post_commit(debate, t, outcome)
    return outcome


async def apply_initial(db: AsyncSession, debate: Debate, transition: tx.Transition) -> Outcome:
    """Persist the state chosen by tx.initial_transition for a newly inserted debate."""
    outcome = Outcome(transition)
    _persist_state(debate, transition.state)
    await _apply_db_effects(db, debate, transition, outcome, turn=None, swarm_config=None, now=utcnow())
    await db.flush()
    _queue_post_commit(debate, transition, outcome)
    return outcome


def _event_time(event: tx.Event) -> datetime:
    return getattr(event, "now", None) or utcnow()


async def _round_row(db: AsyncSession, debate_id: uuid.UUID, round_: Round) -> DebateRound:
    row = await db.scalar(select(DebateRound).where(DebateRound.debate_id == debate_id,
                                                    DebateRound.round == round_.value))
    if row is None:
        row = DebateRound(debate_id=debate_id, round=round_.value)
        db.add(row)
        await db.flush()
    return row


async def _apply_db_effects(db: AsyncSession, debate: Debate, t: tx.Transition, outcome: Outcome, *,
                            turn: TurnPayload | None, swarm_config: dict[str, Any] | None, now: datetime) -> None:
    sides = {Position(s.position): s for s in debate.sides}
    for eff in t.effects:
        match eff:
            case tx.AssignHuman(position=p, user_id=uid):
                sides[p].participant_type = ParticipantType.HUMAN.value
                sides[p].user_id = uid
                sides[p].invited_user_id = None
                sides[p].invite_token = None
            case tx.AssignSwarm(position=p):
                if not swarm_config:
                    raise Conflict("No AI configuration available for the fallback opponent.")
                sides[p].participant_type = ParticipantType.SWARM.value
                sides[p].swarm_config = swarm_config
                sides[p].user_id = None
                sides[p].invited_user_id = None
                sides[p].invite_token = None
            case tx.MarkReady(position=p):
                sides[p].ready_at = now
            case tx.MarkStarted():
                debate.started_at = now
            case tx.StartRound(round=r):
                row = await _round_row(db, debate.id, r)
                row.started_at = now
            case tx.EndRound(round=r):
                row = await _round_row(db, debate.id, r)
                row.ended_at = now
            case tx.OpenRoundVote(round=r, closes_at=closes_at):
                row = await _round_row(db, debate.id, r)
                row.vote_opened_at = now
                row.vote_closes_at = closes_at
            case tx.CloseRoundVote(round=r):
                await close_round_vote(db, debate, r, outcome.outbox, now=now)
            case tx.RecordTurn() as rec:
                outcome.recorded_turns.append(await _record_turn(db, debate, sides[rec.position], rec, turn))
            case tx.MarkCompleted():
                debate.completed_at = now
            case tx.RefundIfCharged(reason=reason):
                await refund_debate(db, debate, reason)
            case tx.FlagForReview(reason=reason):
                db.add(AuditLog(actor_id=None, action="debate_paused", target_type="debate",
                                target_id=str(debate.id), details={"reason": reason}))
                log.error("debate_paused", debate_id=str(debate.id), reason=reason)
            case tx.NotifyTurn(position=p):
                side = sides[p]
                if side.user_id and debate.timing == Timing.ASYNC.value:
                    await _notify_turn(db, debate, side.user_id, outcome.outbox)
            case tx.NotifyCreator(kind=kind):
                if debate.created_by and kind == "fallback_offered":
                    await notify(db, outcome.outbox, debate.created_by, "fallback_offered",
                                 "No challenger yet. Want an AI opponent?", body=debate.question[:200],
                                 link=f"/d/{debate.id}")
            case _:
                pass  # post-commit effects handled in _queue_post_commit


async def _record_turn(db: AsyncSession, debate: Debate, side: Side, rec: tx.RecordTurn,
                       payload: TurnPayload | None) -> Turn:
    if rec.forfeit or payload is None:
        row = Turn(debate_id=debate.id, round=rec.round.value, turn_index=rec.turn_index, side_id=side.id,
                   kind=rec.kind.value, content=FORFEIT_TEXT, word_count=0,
                   source=TurnSource.SWARM.value if side.is_swarm else TurnSource.TYPED.value,
                   is_forfeit=True, moderation_status=ModerationStatus.APPROVED.value)
    else:
        row = Turn(debate_id=debate.id, round=rec.round.value, turn_index=rec.turn_index, side_id=side.id,
                   kind=rec.kind.value, content=payload.content, word_count=payload.word_count,
                   source=payload.source.value, model_key=payload.model_key,
                   idempotency_key=payload.idempotency_key, injection_flag=payload.injection_flag,
                   moderation_status=payload.moderation_status.value, citations=payload.citations,
                   segments=payload.segments,
                   started_ms=payload.started_ms, ended_ms=payload.ended_ms)
    db.add(row)
    await db.flush()
    return row


async def _notify_turn(db: AsyncSession, debate: Debate, user_id: uuid.UUID, outbox: Outbox) -> None:
    await notify(db, outbox, user_id, "your_turn", "Your move.", body=debate.question[:200], link=f"/d/{debate.id}")
    user = await db.get(User, user_id)
    if user and user.email_verified_at and user.status == "active" and user.email_notifications:
        from backend.app.services.email import send_turn_reminder
        email, question, url = user.email, debate.question, f"{get_settings().web_url}/d/{debate.id}"

        async def _send() -> None:
            await send_turn_reminder(email, user_id, question, url)

        outbox.add(_send)


def _queue_post_commit(debate: Debate, t: tx.Transition, outcome: Outcome) -> None:
    debate_id = debate.id
    # Each (re)start of a turn or judging pass gets a fresh deadline, so it makes job ids unique per attempt
    # (a resumed debate must not collide with the ids of the attempts that failed before the pause).
    gen = int(t.state.deadline_at.timestamp() * 1000) if t.state.deadline_at else 0
    for eff in t.effects:
        match eff:
            case tx.ScheduleDeadline(at=at):
                outcome.outbox.add(_job("deadline_check", str(debate_id), at.isoformat(), defer_until=at,
                                        job_id=f"deadline:{debate_id}:{int(at.timestamp())}"))
            case tx.EnqueueSwarmTurn(position=p, round=r, turn_index=i, attempt=a):
                outcome.outbox.add(_job("swarm_turn", str(debate_id), p.value, r.value, i,
                                        job_id=f"swarm:{debate_id}:{r.value}:{i}:{a}:{gen}"))
            case tx.EnqueueJudge(attempt=a):
                outcome.outbox.add(_job("judge_debate", str(debate_id), job_id=f"judge:{debate_id}:{a}:{gen}"))
            case tx.SyncVideo(speakers=speakers):
                outcome.outbox.add(_job("video_sync", str(debate_id), sorted(s.value for s in speakers),
                                        job_id=None))
            case _:
                pass
    for turn in outcome.recorded_turns:
        if not turn.is_forfeit:
            outcome.outbox.add(_job("ledger_extract", str(turn.id), job_id=f"ledger:{turn.id}"))
            if turn.source != TurnSource.SWARM.value or turn.moderation_status == ModerationStatus.UNCHECKED.value:
                outcome.outbox.add(_job("moderate_turn", str(turn.id), job_id=f"moderate:{turn.id}"))

    async def _publish() -> None:
        await publish_debate(debate_id, "state_changed", {"status": t.state.status.value})

    outcome.outbox.add(_publish)


def _job(name: str, *args: Any, defer_until: datetime | None = None, job_id: str | None):
    async def _run() -> None:
        await enqueue(name, *args, defer_until=defer_until, job_id=job_id)
    _run.__name__ = f"enqueue_{name}"
    return _run


# ── Votes (round windows are bookkeeping, not debate state) ────────────────


async def close_round_vote(db: AsyncSession, debate: Debate, round_: Round, outbox: Outbox, *,
                           now: datetime) -> DebateRound | None:
    row = await db.scalar(select(DebateRound).where(DebateRound.debate_id == debate.id,
                                                    DebateRound.round == round_.value).with_for_update(key_share=True))
    if row is None or row.vote_closed_at is not None or row.vote_opened_at is None:
        return row
    side_pos = {s.id: s.position for s in debate.sides}
    votes = (await db.execute(select(Vote.side_id, Vote.weight).where(Vote.debate_id == debate.id,
                                                                      Vote.round == round_.value))).all()
    result = tally([(side_pos.get(sid, ""), w) for sid, w in votes])
    row.vote_closed_at = now
    row.tally = result.as_dict()
    debate_id, payload = debate.id, {"round": round_.value, "tally": row.tally}

    async def _publish() -> None:
        await publish_debate(debate_id, "vote_closed", payload)

    outbox.add(_publish)
    return row
