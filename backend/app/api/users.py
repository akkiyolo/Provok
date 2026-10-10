"""Profiles, settings, avatars, follows, notifications, account deletion/export (DPDP/GDPR)."""
from __future__ import annotations

import io
import secrets
import uuid

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, or_, select, update

from backend.app.api.auth import me_payload
from backend.app.api.deps import DB, CurrentUser, OptionalUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Conflict, NotFound
from backend.app.core.ratelimit import enforce
from backend.app.core.security import utcnow, verify_password
from backend.app.engine.types import UserStatus
from backend.app.models import (
    AuthSession,
    CreditLedger,
    Debate,
    Follow,
    Notification,
    OAuthAccount,
    Payment,
    Side,
    Turn,
    User,
    Vote,
)
from backend.app.services import auth as auth_svc
from backend.app.services import storage
from backend.app.services.debate_view import build_cards

router = APIRouter()


async def _user_by_username(db, username: str) -> User:
    user = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None or user.status in (UserStatus.DELETED, UserStatus.BANNED):
        raise NotFound("User not found.")
    return user


@router.get("/users/{username}")
async def profile(username: str, db: DB, viewer: OptionalUser) -> dict:
    user = await _user_by_username(db, username)
    followers = await db.scalar(select(func.count()).select_from(Follow).where(Follow.followee_id == user.id))
    following = await db.scalar(select(func.count()).select_from(Follow).where(Follow.follower_id == user.id))
    is_following = bool(viewer and await db.scalar(select(Follow.follower_id).where(
        Follow.follower_id == viewer.id, Follow.followee_id == user.id)))
    debate_ids = select(Side.debate_id).where(Side.user_id == user.id)
    recent = list((await db.scalars(select(Debate).where(Debate.id.in_(debate_ids), Debate.is_hidden.is_(False))
                                    .order_by(desc(Debate.created_at)).limit(12))).all())
    rank = await db.scalar(select(func.count()).select_from(User).where(
        User.rating > user.rating, User.status == UserStatus.ACTIVE, (User.wins + User.losses + User.draws) > 0))
    return {
        "id": str(user.id), "username": user.username, "display_name": user.display_name,
        "avatar_url": user.avatar_url, "bio": user.bio, "rating": user.rating, "rank": (rank or 0) + 1,
        "wins": user.wins, "losses": user.losses, "draws": user.draws, "created_at": user.created_at,
        "followers": followers or 0, "following": following or 0, "is_following": is_following,
        "is_me": bool(viewer and viewer.id == user.id), "debates": await build_cards(db, recent),
    }


@router.get("/users/{username}/debates")
async def user_debates(username: str, db: DB, offset: int = Query(default=0, ge=0, le=1000),
                       limit: int = Query(default=20, ge=1, le=50)) -> dict:
    user = await _user_by_username(db, username)
    debate_ids = select(Side.debate_id).where(Side.user_id == user.id)
    rows = list((await db.scalars(select(Debate).where(Debate.id.in_(debate_ids), Debate.is_hidden.is_(False))
                                  .order_by(desc(Debate.created_at)).offset(offset).limit(limit))).all())
    return {"items": await build_cards(db, rows), "next_offset": offset + limit if len(rows) == limit else None}


@router.post("/users/{username}/follow")
async def follow(username: str, user: CurrentUser, db: DB) -> dict:
    await enforce("follow", str(user.id), "60/3600")
    target = await _user_by_username(db, username)
    if target.id == user.id:
        raise AppError("You can't follow yourself.", code="self_follow")
    exists = await db.scalar(select(Follow.follower_id).where(Follow.follower_id == user.id,
                                                              Follow.followee_id == target.id))
    if not exists:
        db.add(Follow(follower_id=user.id, followee_id=target.id))
    await db.commit()
    return {"following": True}


@router.delete("/users/{username}/follow")
async def unfollow(username: str, user: CurrentUser, db: DB) -> dict:
    target = await _user_by_username(db, username)
    await db.execute(delete(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id))
    await db.commit()
    return {"following": False}


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    username: str | None = Field(default=None, max_length=40)
    bio: str | None = Field(default=None, max_length=280)
    onboarded: bool | None = None


@router.patch("/me")
async def update_me(body: ProfileIn, user: CurrentUser, db: DB) -> dict:
    if body.display_name is not None:
        name = auth_svc.clean_display_name(body.display_name)
        if not name:
            raise AppError("Display name can't be empty.", code="invalid_display_name", status_code=422)
        user.display_name = name
    if body.username is not None and body.username.lower() != user.username:
        username = body.username.strip().lower()
        if problem := auth_svc.username_problem(username):
            raise AppError(problem, code="invalid_username", status_code=422)
        if await auth_svc.username_taken(db, username, exclude=user.id):
            raise Conflict("That username is taken.", code="username_taken")
        user.username = username
    if body.bio is not None:
        user.bio = auth_svc.clean_display_name(body.bio.replace("\n", " "))[:280] or None
    if body.onboarded is not None:
        user.onboarded = body.onboarded
    await db.commit()
    return me_payload(user)


ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


@router.post("/me/avatar")
async def upload_avatar(user: CurrentUser, db: DB, file: UploadFile = File(...)) -> dict:
    await enforce("avatar", str(user.id), "10/3600")
    s = get_settings()
    data = await file.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise AppError("Images must be under 5 MB.", code="file_too_large", status_code=413)
    from PIL import Image, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise AppError("Upload a JPEG, PNG, WebP or GIF.", code="bad_image", status_code=415)
        img.seek(0)
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise AppError("That file isn't a valid image.", code="bad_image", status_code=415) from exc
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((400, 400), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=85)  # re-encode: strips metadata (EXIF/GPS) and any embedded payloads
    url = await storage.put_bytes(f"avatars/{user.id}/{secrets.token_hex(8)}.webp", out.getvalue(), "image/webp")
    user.avatar_url = url
    await db.commit()
    return {"avatar_url": url}


@router.get("/me/export")
async def export_my_data(user: CurrentUser, db: DB) -> dict:
    await enforce("export", str(user.id), "3/86400")
    sides = (await db.scalars(select(Side).where(Side.user_id == user.id))).all()
    side_ids = [s.id for s in sides]
    turns = (await db.scalars(select(Turn).where(Turn.side_id.in_(side_ids)))).all() if side_ids else []
    votes = (await db.scalars(select(Vote).where(Vote.user_id == user.id))).all()
    ledger = (await db.scalars(select(CreditLedger).where(CreditLedger.user_id == user.id))).all()
    payments = (await db.scalars(select(Payment).where(Payment.user_id == user.id))).all()
    return {
        "profile": me_payload(user),
        "debates_created": [str(d) for d in (await db.scalars(select(Debate.id).where(
            Debate.created_by == user.id))).all()],
        "turns": [{"debate_id": str(t.debate_id), "round": t.round, "kind": t.kind, "content": t.content,
                   "created_at": t.created_at} for t in turns],
        "votes": [{"debate_id": str(v.debate_id), "round": v.round, "created_at": v.created_at} for v in votes],
        "credit_ledger": [{"delta": e.delta, "reason": e.reason, "created_at": e.created_at} for e in ledger],
        "payments": [{"amount_inr": p.amount_inr, "credits": p.credits, "status": p.status,
                      "created_at": p.created_at} for p in payments],
        "exported_at": utcnow(),
    }


class DeleteIn(BaseModel):
    password: str | None = Field(default=None, max_length=256)
    confirm: str = Field(max_length=40)


@router.post("/me/delete")
async def delete_account(body: DeleteIn, user: CurrentUser, db: DB) -> dict:
    """Anonymise the account. Debate content stays (debates need both sides) but is detached from identity."""
    if body.confirm != "DELETE":
        raise AppError('Type DELETE to confirm.', code="confirm_required", status_code=422)
    if user.password_hash and not verify_password(body.password or "", user.password_hash):
        raise AppError("Your password is incorrect.", code="invalid_credentials", status_code=400)
    anon = f"deleted_{uuid.uuid4().hex[:10]}"
    user.email = f"{anon}@deleted.provok.invalid"
    user.username = anon
    user.display_name = "Deleted user"
    user.bio = None
    user.avatar_url = None
    user.password_hash = None
    user.status = UserStatus.DELETED.value
    user.deleted_at = utcnow()
    user.token_version += 1
    await db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked_at=utcnow()))
    await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == user.id))
    await db.execute(delete(Follow).where(or_(Follow.follower_id == user.id, Follow.followee_id == user.id)))
    await db.execute(delete(Notification).where(Notification.user_id == user.id))
    await db.commit()
    return {"ok": True}


# ── Notifications ──────────────────────────────────────────────────────────


@router.get("/notifications")
async def notifications(user: CurrentUser, db: DB, limit: int = Query(default=30, ge=1, le=100)) -> dict:
    rows = (await db.scalars(select(Notification).where(Notification.user_id == user.id)
                             .order_by(desc(Notification.created_at)).limit(limit))).all()
    unread = await db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"items": [{"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                       "read": n.read_at is not None, "created_at": n.created_at} for n in rows],
            "unread": unread or 0}


class ReadIn(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


@router.post("/notifications/read")
async def mark_read(body: ReadIn, user: CurrentUser, db: DB) -> dict:
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if body.ids:
        q = q.where(Notification.id.in_(body.ids))
    await db.execute(q.values(read_at=utcnow()))
    await db.commit()
    return {"ok": True}
