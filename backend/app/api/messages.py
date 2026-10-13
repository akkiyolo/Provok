"""Direct messages API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.api.deps import DB, ActiveDebater, CurrentUser
from backend.app.core.config import get_settings
from backend.app.core.errors import NotFound
from backend.app.core.ratelimit import enforce
from backend.app.models import User
from backend.app.models.social import DM_MAX_CHARS
from backend.app.services import messages as svc
from backend.app.services.debate_view import public_user
from backend.app.services.outbox import Outbox

router = APIRouter()


@router.get("/conversations")
async def conversations(user: CurrentUser, db: DB) -> dict:
    return {"items": await svc.inbox(db, user)}


@router.get("/conversations/unread")
async def unread(user: CurrentUser, db: DB) -> dict:
    return {"unread": await svc.unread_count(db, user)}


@router.post("/conversations/with/{username}")
async def start(username: str, user: ActiveDebater, db: DB) -> dict:
    other = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if other is None:
        raise NotFound("User not found.")
    convo, created = await svc.open_conversation(db, user, other)
    if created:
        await enforce("dm_new", str(user.id), get_settings().rl_dm_new_user,
                      "You've started a lot of new conversations today. Try again tomorrow.")
    await db.commit()
    return {"id": str(convo.id), "with": public_user(other)}


@router.get("/conversations/{convo_id}")
async def get_conversation(convo_id: uuid.UUID, user: CurrentUser, db: DB,
                           cursor: str | None = Query(default=None, max_length=200)) -> dict:
    convo = await svc.get_conversation(db, convo_id, user)
    other = await db.get(User, svc.other_id(convo, user.id))
    items, nxt = await svc.messages_page(db, convo, user, cursor)
    if cursor is None:
        await svc.mark_read(convo, user)
        await db.commit()
    return {"id": str(convo.id), "with": public_user(other), "items": items, "next_cursor": nxt}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=DM_MAX_CHARS * 2)


@router.post("/conversations/{convo_id}/messages", status_code=201)
async def send(convo_id: uuid.UUID, body: MessageIn, user: ActiveDebater, db: DB) -> dict:
    await enforce("dm", str(user.id), get_settings().rl_dm_user, "You're sending messages very fast. Slow down a little.")
    convo = await svc.get_conversation(db, convo_id, user, lock=True)
    outbox = Outbox()
    msg = await svc.send(db, outbox, user, convo, body.text)
    await db.commit()
    await outbox.flush()
    return svc.message_view(msg, user.id)


@router.post("/conversations/{convo_id}/read")
async def read(convo_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    convo = await svc.get_conversation(db, convo_id, user)
    await svc.mark_read(convo, user)
    await db.commit()
    return {"ok": True}
