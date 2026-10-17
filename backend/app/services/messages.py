"""Direct messages: one-to-one conversations.

Anyone verified can message anyone they haven't blocked (or been blocked by). A conversation from someone you
don't follow lands in Requests until you reply, so strangers can't fill your inbox. Messages aren't end-to-end
encrypted; the privacy policy says so.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, desc, exists, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError, Forbidden, NotFound
from backend.app.core.security import utcnow
from backend.app.models import Conversation, DirectMessage, Follow, User
from backend.app.models.social import DM_MAX_CHARS
from backend.app.realtime.publish import publish_user
from backend.app.services.debate_view import public_user
from backend.app.services.notify import queue_push
from backend.app.services.outbox import Outbox
from backend.app.services.posts import VISIBLE_AUTHOR_STATUSES, clean_text, decode_cursor, encode_cursor, is_blocked
from backend.app.services.push import make_payload

PAGE = 30


def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


def other_id(c: Conversation, me: uuid.UUID) -> uuid.UUID:
    return c.user_b if c.user_a == me else c.user_a


def _is_member(c: Conversation, me: uuid.UUID) -> bool:
    return me in (c.user_a, c.user_b)


async def open_conversation(db: AsyncSession, me: User, other: User) -> tuple[Conversation, bool]:
    if other.id == me.id:
        raise AppError("You can't message yourself.", code="self_message", status_code=422)
    if other.status not in VISIBLE_AUTHOR_STATUSES:
        raise NotFound("User not found.")
    if await is_blocked(db, me.id, other.id):
        raise Forbidden("You can't message this account.", code="blocked")
    a, b = _pair(me.id, other.id)
    convo = await db.scalar(select(Conversation).where(Conversation.user_a == a, Conversation.user_b == b))
    if convo is not None:
        return convo, False
    convo = Conversation(user_a=a, user_b=b)
    db.add(convo)
    await db.flush()
    return convo, True


async def get_conversation(db: AsyncSession, convo_id: uuid.UUID, me: User, *, lock: bool = False) -> Conversation:
    q = select(Conversation).where(Conversation.id == convo_id)
    if lock:
        q = q.with_for_update()
    convo = await db.scalar(q)
    if convo is None or not _is_member(convo, me.id):
        raise NotFound("Conversation not found.")
    return convo


async def send(db: AsyncSession, outbox: Outbox, me: User, convo: Conversation, text: str) -> DirectMessage:
    body = clean_text(text)
    if not body:
        raise AppError("Write a message.", code="empty_message", status_code=422)
    if len(body) > DM_MAX_CHARS:
        raise AppError(f"Messages can be up to {DM_MAX_CHARS} characters.", code="too_long", status_code=422)
    other = other_id(convo, me.id)
    if await is_blocked(db, me.id, other):
        raise Forbidden("You can't message this account.", code="blocked")
    msg = DirectMessage(conversation_id=convo.id, sender_id=me.id, text=body)
    db.add(msg)
    now = utcnow()
    convo.last_message_at = now
    if convo.user_a == me.id:
        convo.a_read_at = now
    else:
        convo.b_read_at = now
    await db.flush()
    payload = {"conversation_id": str(convo.id), "id": str(msg.id), "sender": me.username, "text": body[:200]}

    async def _push() -> None:
        await publish_user(other, "dm", payload)

    outbox.add(_push)
    queue_push(outbox, other, make_payload("dm", f"{me.display_name} sent you a message", body,
                                           f"/messages/{convo.id}", tag=f"dm-{convo.id}"[:32]),
               job_id=f"push:{msg.id}")
    return msg


def message_view(m: DirectMessage, me: uuid.UUID) -> dict[str, Any]:
    return {"id": str(m.id), "text": m.text, "mine": m.sender_id == me, "created_at": m.created_at}


async def messages_page(db: AsyncSession, convo: Conversation, me: User, cursor: str | None):
    """Newest first; the client shows them oldest at the top."""
    c = decode_cursor(cursor)
    rows = list((await db.scalars(select(DirectMessage).where(
        DirectMessage.conversation_id == convo.id,
        tuple_(DirectMessage.created_at, DirectMessage.id) < (c[0], c[1]) if c else literal(True))
        .order_by(desc(DirectMessage.created_at), desc(DirectMessage.id)).limit(PAGE + 1))).all())
    nxt = encode_cursor(rows[PAGE - 1].created_at, rows[PAGE - 1].id) if len(rows) > PAGE else None
    return [message_view(m, me.id) for m in rows[:PAGE]], nxt


def _read_at(c: Conversation, me: uuid.UUID):
    return c.a_read_at if c.user_a == me else c.b_read_at


async def mark_read(convo: Conversation, me: User) -> None:
    if convo.user_a == me.id:
        convo.a_read_at = utcnow()
    else:
        convo.b_read_at = utcnow()


async def inbox(db: AsyncSession, me: User) -> list[dict[str, Any]]:
    convos = list((await db.scalars(select(Conversation).where(
        or_(Conversation.user_a == me.id, Conversation.user_b == me.id), Conversation.last_message_at.is_not(None))
        .order_by(desc(Conversation.last_message_at)).limit(100))).all())
    if not convos:
        return []
    others = {u.id: u for u in (await db.scalars(select(User).where(
        User.id.in_({other_id(c, me.id) for c in convos})))).all()}
    following = set((await db.scalars(select(Follow.followee_id).where(
        Follow.follower_id == me.id, Follow.followee_id.in_(others.keys())))).all())
    replied = set((await db.scalars(select(DirectMessage.conversation_id).where(
        DirectMessage.sender_id == me.id, DirectMessage.conversation_id.in_([c.id for c in convos]))
        .distinct())).all())
    last: dict[uuid.UUID, DirectMessage] = {}
    latest = (select(DirectMessage.conversation_id, func.max(DirectMessage.created_at).label("at"))
              .where(DirectMessage.conversation_id.in_([c.id for c in convos]))
              .group_by(DirectMessage.conversation_id).subquery())
    for m in (await db.scalars(select(DirectMessage).join(latest, and_(
            DirectMessage.conversation_id == latest.c.conversation_id, DirectMessage.created_at == latest.c.at)))).all():
        last[m.conversation_id] = m
    out = []
    for c in convos:
        other = others.get(other_id(c, me.id))
        if other is None or other.status not in VISIBLE_AUTHOR_STATUSES:
            continue
        read = _read_at(c, me.id)
        m = last.get(c.id)
        out.append({
            "id": str(c.id), "with": public_user(other),
            "last": message_view(m, me.id) if m else None, "last_message_at": c.last_message_at,
            "unread": bool(c.last_message_at and (read is None or c.last_message_at > read)),
            # From someone you don't follow, and you've never replied: a request, not your inbox.
            "request": other.id not in following and c.id not in replied,
        })
    return out


async def unread_count(db: AsyncSession, me: User) -> int:
    mine_a, mine_b = Conversation.user_a == me.id, Conversation.user_b == me.id
    unread = or_(
        and_(mine_a, or_(Conversation.a_read_at.is_(None), Conversation.last_message_at > Conversation.a_read_at)),
        and_(mine_b, or_(Conversation.b_read_at.is_(None), Conversation.last_message_at > Conversation.b_read_at)),
    )
    # Requests (strangers you never answered) don't light up the badge.
    followed = select(Follow.followee_id).where(Follow.follower_id == me.id)
    other = func.coalesce(func.nullif(Conversation.user_a, me.id), Conversation.user_b)
    replied = exists().where(DirectMessage.conversation_id == Conversation.id, DirectMessage.sender_id == me.id)
    n = await db.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.last_message_at.is_not(None), unread, or_(other.in_(followed), replied)))
    return n or 0
