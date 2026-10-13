"""The Daily Debate: every morning the official @provok account posts a question with a Yes/No poll, and an
AI-vs-AI debate on it starts in the Arena, linked to the post."""
from __future__ import annotations

import random
import uuid
from datetime import date
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.models import DailyDebate, Debate, Post, User
from backend.app.services.featured import create_featured, load_questions
from backend.app.services.outbox import Outbox

log = get_logger("provok.daily")

OFFICIAL_USERNAME = "provok"
POLL_HOURS = 24


async def official_user(db: AsyncSession) -> User:
    """@provok, created on first use. 'provok' is a reserved username, so nobody else can register it."""
    user = await db.scalar(select(User).where(User.username == OFFICIAL_USERNAME))
    if user is None:
        user = User(email="official@provok.in", email_verified_at=utcnow(), username=OFFICIAL_USERNAME,
                    display_name="Provok", bio="The arena for ideas. A new Daily Debate every morning.",
                    is_official=True)
        db.add(user)
        await db.flush()
    return user


def _pick_question(used: set[str]) -> dict[str, Any]:
    bank = load_questions()
    fresh = [q for q in bank if q["question"] not in used]
    return random.choice(fresh or bank)


async def create_daily(day: date | None = None) -> DailyDebate | None:
    """Idempotent per day: a second call for the same day does nothing."""
    from backend.app.services import posts as posts_svc
    day = day or utcnow().date()
    async with session_scope() as db:
        if await db.get(DailyDebate, day) is not None:
            return None
        used = set((await db.scalars(select(DailyDebate.question))).all())
        item = _pick_question(used)
        author = await official_user(db)
        outbox = Outbox()
        post = await posts_svc.create_post(
            db, outbox, author, text=f"Daily Debate: {item['question']}\n\nVote, then argue it out. #DailyDebate",
            media_ids=[], reply_to_id=None, quote_of_id=None, poll=["Yes", "No"], poll_hours=POLL_HOURS)
        daily = DailyDebate(day=day, question=item["question"], post_id=post.id)
        db.add(daily)
        post_id = post.id
    created = await create_featured(items=[item], source_post_id=post_id)  # empty when AI debates are paused
    if created:
        async with session_scope() as db:
            row = await db.get(DailyDebate, day)
            if row is not None:
                row.debate_id = uuid.UUID(created[0])
    log.info("daily_debate_created", day=str(day), question=item["question"], debate_id=created[0] if created else None)
    async with session_scope() as db:
        return await db.get(DailyDebate, day)


async def latest_daily(db: AsyncSession) -> tuple[DailyDebate, Post | None, Debate | None] | None:
    row = await db.scalar(select(DailyDebate).order_by(desc(DailyDebate.day)).limit(1))
    if row is None:
        return None
    post = await db.scalar(select(Post).where(Post.id == row.post_id, Post.status == "visible")) if row.post_id else None
    debate = await db.scalar(select(Debate).where(Debate.id == row.debate_id, Debate.is_hidden.is_(False))) \
        if row.debate_id else None
    return row, post, debate
