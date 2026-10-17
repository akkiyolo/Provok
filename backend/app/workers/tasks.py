"""
Background jobs (ARQ). Every job is idempotent and re-validates state under a
row lock before acting, so duplicate or late jobs are harmless.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.engine import transitions as tx
from backend.app.engine.service import (
    TurnPayload,
    apply_event,
    close_round_vote,
    get_debate_for_update,
)
from backend.app.engine.types import ModerationStatus, Position, Round, Status, Timing, TurnSource
from backend.app.judge.judge import JudgingError, judge_debate
from backend.app.ledger.extract import extract_claims
from backend.app.llm.gateway import LLMError
from backend.app.models import AnalyticsEvent, Debate, DebateRound, LLMCall, Post, Turn, User
from backend.app.moderation.content import moderate
from backend.app.realtime.publish import publish_debate
from backend.app.services import flags
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox
from backend.app.swarm.pipeline import load_context, run_pipeline, stream_typing

log = get_logger("provok.worker")


async def _apply_and_flush(debate_id: uuid.UUID, make_event, **kwargs: Any) -> tx.Transition | None:
    """Lock the debate, apply an event, commit, then flush post-commit effects."""
    outbox = Outbox()
    t = None
    async with session_scope() as db:
        debate = await get_debate_for_update(db, debate_id)
        try:
            outcome = await apply_event(db, debate, make_event(debate), **kwargs)
        except tx.StaleEvent:
            return None
        except tx.InvalidTransition as exc:
            log.info("job_event_rejected", debate_id=str(debate_id), code=exc.code)
            return None
        outbox.extend(outcome.outbox)
        t = outcome.transition
    await outbox.flush()
    return t


# ── Timers ─────────────────────────────────────────────────────────────────


async def deadline_check(ctx: dict, debate_id: str, deadline_iso: str) -> None:
    expected = datetime.fromisoformat(deadline_iso)
    await _handle_deadline(uuid.UUID(debate_id), expected)


async def _handle_deadline(debate_id: uuid.UUID, expected: datetime | None) -> None:
    async with session_scope() as db:
        debate = await db.get(Debate, debate_id)
        if debate is None or debate.deadline_at is None or debate.deadline_at > utcnow():
            return
        timing, round_, idx = debate.timing, debate.current_round, debate.current_turn_index
    # Video: a debater who spoke but didn't press "end turn" still gets their transcript submitted.
    if timing == Timing.VIDEO.value and round_:
        from backend.app.video.transcripts import submit_transcript_if_any
        if await submit_transcript_if_any(debate_id, Round(round_), idx):
            return
    await _apply_and_flush(debate_id, lambda d: tx.DeadlineExpired(utcnow(), expected_deadline_at=expected))


async def sweeper(ctx: dict) -> None:
    """Safety net: fires overdue deadlines and closes overdue vote windows even if jobs were lost."""
    now = utcnow()
    async with session_scope() as db:
        overdue = (await db.scalars(
            select(Debate.id).where(Debate.deadline_at.is_not(None), Debate.deadline_at <= now - timedelta(seconds=2),
                                    Debate.status.not_in([s.value for s in Status if s.is_terminal]))
            .order_by(Debate.deadline_at).limit(50))).all()
        votes_due = (await db.execute(
            select(DebateRound.debate_id, DebateRound.round).where(
                DebateRound.vote_closed_at.is_(None), DebateRound.vote_closes_at.is_not(None),
                DebateRound.vote_closes_at <= now).limit(100))).all()
    for debate_id in overdue:
        try:
            await _handle_deadline(debate_id, None)
        except Exception as exc:
            log.error("sweeper_deadline_failed", debate_id=str(debate_id), error=str(exc))
    for debate_id, round_ in votes_due:
        await close_vote_job(ctx, str(debate_id), round_)
    await _auto_resume(now)


AUTO_RESUMABLE = ("swarm_error", "swarm_timeout", "judge_timeout", "judge_error")


async def _auto_resume(now: datetime) -> None:
    """Provider outages are usually brief: retry paused debates a few times before a human has to step in."""
    from backend.app.core.redis import get_redis
    s = get_settings()
    async with session_scope() as db:
        candidates = (await db.scalars(
            select(Debate.id).where(Debate.status == Status.PAUSED.value,
                                    Debate.updated_at <= now - timedelta(seconds=s.auto_resume_after_seconds))
            .where(Debate.paused_reason.in_(AUTO_RESUMABLE) | Debate.paused_reason.like("judge%"))
            .limit(20))).all()
    r = get_redis()
    for debate_id in candidates:
        key, wait_key = f"autoresume:{debate_id}", f"autoresume:wait:{debate_id}"
        if await r.exists(wait_key):
            continue
        attempts = await r.incr(key)
        if attempts == 1:  # the day starts at the first retry; refreshing it on every sweep made it never end
            await r.expire(key, 86400)
        if attempts > s.auto_resume_max_attempts:
            continue
        # Back off (5, 15, 45 min with the defaults): a provider that failed twice in a row is rarely back in 5.
        await r.set(wait_key, 1, ex=s.auto_resume_after_seconds * 3 ** attempts)
        log.info("debate_auto_resume", debate_id=str(debate_id), attempt=attempts)
        await _apply_and_flush(debate_id, lambda d: tx.Resumed(utcnow()))


async def close_vote_job(ctx: dict, debate_id: str, round_: str) -> None:
    outbox = Outbox()
    async with session_scope() as db:
        debate = await db.get(Debate, uuid.UUID(debate_id))
        if debate is None:
            return
        await db.refresh(debate, ["sides"])
        await close_round_vote(db, debate, Round(round_), outbox, now=utcnow())
    await outbox.flush()


# ── Swarm ──────────────────────────────────────────────────────────────────


async def swarm_turn(ctx: dict, debate_id: str, position: str, round_: str, turn_index: int) -> None:
    did, pos, rnd = uuid.UUID(debate_id), Position(position), Round(round_)
    async with session_scope() as db:
        debate = await db.get(Debate, did)
        if debate is None:
            return
        await db.refresh(debate, ["sides"])
        if not (Status(debate.status).is_round and debate.current_round == rnd.value
                and debate.current_turn_index == turn_index):
            return  # stale job
        kind = tx.expected_turn(rnd, turn_index)[1]
        try:
            context = await load_context(db, debate, pos, rnd, kind)
            output = await run_pipeline(db, context)
        except (LLMError, KeyError, ValueError) as exc:
            log.error("swarm_turn_failed", debate_id=debate_id, error=str(exc))
            output = None
    if output is None:
        await _apply_and_flush(did, lambda d: tx.SwarmFailed(pos, rnd, turn_index, utcnow(), "swarm_error"))
        return
    await stream_typing(did, pos, output.content)
    payload = TurnPayload(content=output.content, word_count=output.word_count, source=TurnSource.SWARM,
                          model_key=output.model_key, citations=output.citations,
                          idempotency_key=f"swarm:{rnd.value}:{turn_index}")

    def _event(d: Debate) -> tx.Event:
        if d.current_round != rnd.value or d.current_turn_index != turn_index:
            raise tx.StaleEvent("stale", "turn moved on")
        return tx.TurnSubmitted(pos, kind, output.word_count, utcnow(), is_swarm=True)

    try:
        await _apply_and_flush(did, _event, turn=payload)
    except tx.StaleEvent:
        pass


# ── Ledger & moderation ────────────────────────────────────────────────────


async def ledger_extract(ctx: dict, turn_id: str) -> None:
    async with session_scope() as db:
        created = await extract_claims(db, uuid.UUID(turn_id))
        debate_id = (await db.get(Turn, uuid.UUID(turn_id))).debate_id if created else None
    if debate_id:
        await publish_debate(debate_id, "ledger_updated", {"turn_id": turn_id})


async def moderate_turn(ctx: dict, turn_id: str) -> None:
    outbox = Outbox()
    async with session_scope() as db:
        turn = await db.scalar(select(Turn).where(Turn.id == uuid.UUID(turn_id)).with_for_update(key_share=True))
        if turn is None or turn.moderation_status in (ModerationStatus.HIDDEN, ModerationStatus.APPROVED):
            return
        result = await moderate(turn.content, debate_id=turn.debate_id)
        if result.flagged:
            turn.moderation_status = ModerationStatus.FLAGGED.value
            turn.moderation_reason = ", ".join(result.categories)[:200] or result.reason
            log.warning("turn_flagged", turn_id=turn_id, categories=result.categories)
            admins = (await db.scalars(select(User.id).where(User.role == "admin"))).all()
            for admin_id in admins[:5]:
                await notify(db, outbox, admin_id, "moderation", "A turn was flagged for review",
                             body=turn.moderation_reason, link="/admin")
        else:
            turn.moderation_status = (ModerationStatus.APPROVED if result.checked else ModerationStatus.UNCHECKED).value
        debate_id, flagged = turn.debate_id, result.flagged
    await outbox.flush()
    if flagged:
        await publish_debate(debate_id, "state_changed", {"reason": "moderation"})


async def link_preview(ctx: dict, post_id: str) -> None:
    from backend.app.services.link_preview import attach_preview
    await attach_preview(uuid.UUID(post_id))


async def send_push(ctx: dict, user_id: str, payload: dict) -> None:
    from backend.app.services.push import send_to_user
    await send_to_user(uuid.UUID(user_id), payload)


async def factcheck_post(ctx: dict, post_id: str) -> None:
    from backend.app.services.post_ai import run_factcheck
    await run_factcheck(uuid.UUID(post_id))


async def moderate_post(ctx: dict, post_id: str) -> None:
    """Posts go live immediately; the model checks them right after. Flagged posts are hidden until a moderator
    looks (Admin → Reports), and the author is told."""
    outbox = Outbox()
    async with session_scope() as db:
        post = await db.scalar(select(Post).where(Post.id == uuid.UUID(post_id)).with_for_update(key_share=True))
        if post is None or post.status != "visible" or not post.text:
            return
        result = await moderate(post.text)
        if not result.flagged:
            return
        post.status = "hidden"
        post.moderation_reason = (", ".join(result.categories) or result.reason or "flagged")[:200]
        log.warning("post_flagged", post_id=post_id, categories=result.categories)
        await notify(db, outbox, post.author_id, "moderation", "Your post was hidden for review",
                     body="It may break our community rules. A moderator will take a look.", link=f"/p/{post.id}")
        admins = (await db.scalars(select(User.id).where(User.role == "admin"))).all()
        for admin_id in admins[:5]:
            await notify(db, outbox, admin_id, "moderation", "A post was hidden for review",
                         body=post.moderation_reason, link="/admin")
    await outbox.flush()


# ── Judge ──────────────────────────────────────────────────────────────────


async def judge_job(ctx: dict, debate_id: str) -> None:
    """Judging takes minutes of LLM calls, so it must never hold a row lock while it works:
    a Redis lock prevents concurrent judging, and the debate row is locked only to commit the result."""
    from backend.app.core.redis import get_redis
    did = uuid.UUID(debate_id)
    lock_key = f"judging:{did}"
    if not await get_redis().set(lock_key, "1", nx=True, ex=1200):
        return
    outbox = Outbox()
    try:
        async with session_scope() as db:
            debate = await db.get(Debate, did)
            if debate is None or debate.status != Status.JUDGING.value:
                return
            await db.refresh(debate, ["sides"])
            await judge_debate(db, debate, attempt=debate.swarm_retry_count)  # idempotent: reuses an existing verdict
        async with session_scope() as db:
            debate = await get_debate_for_update(db, did)
            if debate.status != Status.JUDGING.value:
                return
            outcome = await apply_event(db, debate, tx.JudgingDone(utcnow()))
            for uid in [s.user_id for s in debate.sides if s.user_id]:
                await notify(db, outcome.outbox, uid, "verdict", "The verdict is in.", body=debate.question[:200],
                             link=f"/d/{did}/verdict")
            db.add(AnalyticsEvent(name="debate_completed", debate_id=did,
                                  props={"mode": debate.mode, "timing": debate.timing}))
            outbox.extend(outcome.outbox)
            timing = debate.timing
    except (JudgingError, LLMError) as exc:
        reason = str(exc)[:100]
        log.error("judging_failed", debate_id=debate_id, error=reason)
        await get_redis().delete(lock_key)
        await _apply_and_flush(did, lambda d: tx.JudgingFailed(utcnow(), reason))
        return
    finally:
        await get_redis().delete(lock_key)
    await outbox.flush()
    await publish_debate(did, "verdict_ready", {"debate_id": debate_id})
    await _email_verdict(did)
    if timing == Timing.VIDEO.value:
        from backend.app.workers.queue import enqueue
        await enqueue("generate_clips", debate_id, job_id=f"clips:{debate_id}")


async def _email_verdict(debate_id: uuid.UUID) -> None:
    from backend.app.services.email import send_debate_result
    async with session_scope() as db:
        debate = await db.get(Debate, debate_id)
        if debate is None:
            return
        await db.refresh(debate, ["sides"])
        ids = [s.user_id for s in debate.sides if s.user_id]
        users = (await db.scalars(select(User).where(User.id.in_(ids)))).all() if ids else []
        recipients = [(u.email, u.id) for u in users
                      if u.email_verified_at and u.status == "active" and u.email_notifications]
        question = debate.question
    if debate.timing == Timing.ASYNC.value:
        url = f"{get_settings().web_url}/d/{debate_id}/verdict"
        for email, user_id in recipients:
            await send_debate_result(email, user_id, question, url)


# ── Ops ────────────────────────────────────────────────────────────────────


async def spend_check(ctx: dict) -> None:
    """If today's LLM spend exceeds the alert threshold, alert and stop new AI debates."""
    limit = get_settings().daily_llm_spend_alert_usd
    if not limit:
        return
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    async with session_scope() as db:
        spent = float(await db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))
                                      .where(LLMCall.created_at >= start)) or 0)
        if spent > limit and await flags.is_enabled(flags.AI_DEBATES):
            await flags.set_flag(db, flags.AI_DEBATES, False, f"Auto-disabled: daily spend ${spent:.2f} > ${limit}")
            log.critical("llm_spend_kill_switch", spent_usd=spent, limit_usd=limit)
            try:
                import sentry_sdk
                sentry_sdk.capture_message(f"LLM spend kill switch tripped: ${spent:.2f}", level="fatal")
            except Exception:
                pass


async def daily_debate_job(ctx: dict) -> None:
    from backend.app.services.daily import create_daily
    await create_daily()


async def featured_job(ctx: dict) -> None:
    from backend.app.services.featured import create_featured
    await create_featured(get_settings().featured_ava_per_run)


async def heartbeat(ctx: dict) -> None:
    from backend.app.core.redis import get_redis
    await get_redis().set("worker:heartbeat", utcnow().isoformat(), ex=120)


async def video_sync(ctx: dict, debate_id: str, speakers: list[str]) -> None:
    from backend.app.video.livekit import sync_mute
    await sync_mute(uuid.UUID(debate_id), set(speakers))


async def generate_clips(ctx: dict, debate_id: str) -> None:
    from backend.app.video.clips import generate_clips_for_debate
    await generate_clips_for_debate(uuid.UUID(debate_id))

