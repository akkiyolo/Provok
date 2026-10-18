"""Profiles, settings, avatars, follows, notifications, account deletion/export (DPDP/GDPR)."""
from __future__ import annotations

import io
import re
import secrets
import uuid

import jwt
from fastapi import APIRouter, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, or_, select, update

from backend.app.api.auth import me_payload
from backend.app.api.deps import DB, CurrentUser, OptionalUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Conflict, Forbidden, NotFound
from backend.app.core.ratelimit import enforce
from backend.app.core.security import decode_jwt, utcnow, verify_password
from backend.app.engine.types import UserStatus
from backend.app.models import (
    AuthSession,
    Bookmark,
    Conversation,
    CreditLedger,
    Debate,
    DirectMessage,
    Follow,
    Notification,
    OAuthAccount,
    Payment,
    Post,
    PostLike,
    PushSubscription,
    Side,
    Turn,
    User,
    UserBlock,
    UserMute,
    Vote,
)
from backend.app.services import auth as auth_svc
from backend.app.services import posts as posts_svc
from backend.app.services import push as push_svc
from backend.app.services import referrals, storage
from backend.app.services.debate_view import build_cards
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox

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
    blocked_by_me = bool(viewer and await db.scalar(select(UserBlock.blocker_id).where(
        UserBlock.blocker_id == viewer.id, UserBlock.blocked_id == user.id)))
    blocks_me = bool(viewer and await db.scalar(select(UserBlock.blocker_id).where(
        UserBlock.blocker_id == user.id, UserBlock.blocked_id == viewer.id)))
    muted = bool(viewer and await db.scalar(select(UserMute.muter_id).where(
        UserMute.muter_id == viewer.id, UserMute.muted_id == user.id)))
    pinned = None
    if user.pinned_post_id and not blocks_me:
        pinned_post = await db.scalar(select(Post).where(Post.id == user.pinned_post_id, Post.status == "visible"))
        if pinned_post is not None:
            pinned = (await posts_svc.build_views(db, [pinned_post], viewer) or [None])[0]
    posts_count = await db.scalar(select(func.count()).select_from(Post).where(
        Post.author_id == user.id, Post.status == "visible", Post.kind == "post"))
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
        "posts_count": posts_count or 0, "is_blocked": blocked_by_me, "blocks_you": blocks_me, "is_muted": muted,
        "banner_url": user.banner_url, "website": user.website, "location": user.location,
        "verified": user.is_official, "pinned": pinned,
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
    if await posts_svc.is_blocked(db, user.id, target.id):
        raise Forbidden("You can't follow this account.", code="blocked")
    exists = await db.scalar(select(Follow.follower_id).where(Follow.follower_id == user.id,
                                                              Follow.followee_id == target.id))
    outbox = Outbox()
    if not exists:
        db.add(Follow(follower_id=user.id, followee_id=target.id))
        await notify(db, outbox, target.id, "follow", f"{user.display_name} followed you",
                     link=f"/u/{user.username}")
    await db.commit()
    await outbox.flush()
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
    email_notifications: bool | None = None
    website: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=60)


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
    if body.email_notifications is not None:
        user.email_notifications = body.email_notifications
    if body.website is not None:
        site = body.website.strip()
        if site and not site.lower().startswith(("http://", "https://")):
            site = f"https://{site}"
        if site and not re.fullmatch(r"https?://[^\s/$.?#][^\s]*", site):
            raise AppError("That doesn't look like a web address.", code="invalid_website", status_code=422)
        user.website = site or None
    if body.location is not None:
        user.location = auth_svc.clean_display_name(body.location)[:60] or None
    await db.commit()
    return me_payload(user)


@router.post("/email/unsubscribe")
async def unsubscribe(db: DB, token: str = Query(max_length=2000)) -> dict:
    """No sign-in: the signed token is the authorisation. Serves the /unsubscribe page and RFC 8058 one-click
    POSTs from mail clients (Gmail's "Unsubscribe" button), which carry the token in the URL."""
    try:
        user_id = uuid.UUID(decode_jwt(token, "unsubscribe")["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise AppError("This unsubscribe link is invalid or has expired.", code="invalid_token") from exc
    await db.execute(update(User).where(User.id == user_id).values(email_notifications=False))
    await db.commit()
    return {"ok": True}


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


@router.post("/me/banner")
async def upload_banner(user: CurrentUser, db: DB, file: UploadFile = File(...)) -> dict:
    """Profile cover photo: centre-cropped to 3:1 and re-encoded (strips metadata)."""
    await enforce("avatar", str(user.id), "10/3600")
    s = get_settings()
    data = await file.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise AppError("Images must be under 5 MB.", code="file_too_large", status_code=413)
    from PIL import Image, ImageOps, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise AppError("Upload a JPEG, PNG, WebP or GIF.", code="bad_image", status_code=415)
        img.seek(0)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise AppError("That file isn't a valid image.", code="bad_image", status_code=415) from exc
    img = ImageOps.fit(img, (1500, 500), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=82)
    # Under avatars/ so it's publicly readable alongside the profile photo.
    url = await storage.put_bytes(f"avatars/{user.id}/banner-{secrets.token_hex(8)}.webp", out.getvalue(), "image/webp")
    user.banner_url = url
    await db.commit()
    return {"banner_url": url}


@router.get("/me/export")
async def export_my_data(user: CurrentUser, db: DB) -> dict:
    await enforce("export", str(user.id), "3/86400")
    sides = (await db.scalars(select(Side).where(Side.user_id == user.id))).all()
    side_ids = [s.id for s in sides]
    turns = (await db.scalars(select(Turn).where(Turn.side_id.in_(side_ids)))).all() if side_ids else []
    votes = (await db.scalars(select(Vote).where(Vote.user_id == user.id))).all()
    ledger = (await db.scalars(select(CreditLedger).where(CreditLedger.user_id == user.id))).all()
    payments = (await db.scalars(select(Payment).where(Payment.user_id == user.id))).all()
    my_posts = (await db.scalars(select(Post).where(Post.author_id == user.id, Post.status != "deleted")
                                 .order_by(Post.created_at))).all()
    likes = (await db.scalars(select(PostLike).where(PostLike.user_id == user.id))).all()
    sent = (await db.scalars(select(DirectMessage).where(DirectMessage.sender_id == user.id)
                             .order_by(DirectMessage.created_at))).all()
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
        "posts": [{"id": str(x.id), "kind": x.kind, "text": x.text, "reply_to_id": str(x.reply_to_id or "") or None,
                   "quote_of_id": str(x.quote_of_id or "") or None, "repost_of_id": str(x.repost_of_id or "") or None,
                   "created_at": x.created_at} for x in my_posts],
        "likes": [{"post_id": str(x.post_id), "created_at": x.created_at} for x in likes],
        "messages_sent": [{"conversation_id": str(m.conversation_id), "text": m.text, "created_at": m.created_at}
                          for m in sent],
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
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))
    await db.execute(update(Post).where(Post.author_id == user.id).values(status="deleted"))
    await db.execute(delete(PostLike).where(PostLike.user_id == user.id))
    await db.execute(delete(Bookmark).where(Bookmark.user_id == user.id))
    await db.execute(delete(UserBlock).where(or_(UserBlock.blocker_id == user.id, UserBlock.blocked_id == user.id)))
    await db.execute(delete(UserMute).where(or_(UserMute.muter_id == user.id, UserMute.muted_id == user.id)))
    await db.execute(delete(Conversation).where(or_(Conversation.user_a == user.id, Conversation.user_b == user.id)))
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


# ── Web push ───────────────────────────────────────────────────────────────


@router.get("/push/config")
async def push_config() -> dict:
    s = get_settings()
    return {"enabled": s.push_enabled, "public_key": s.vapid_public_key if s.push_enabled else None}


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_-]+=*$")
    auth: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+=*$")


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: PushKeys


class PushEndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.post("/me/push-subscriptions")
async def subscribe_push(body: PushSubscriptionIn, request: Request, user: CurrentUser, db: DB) -> dict:
    if not get_settings().push_enabled:
        raise AppError("Push notifications aren't available yet.", code="push_disabled", status_code=409)
    await enforce("push_subscribe", str(user.id), "30/3600")
    if not push_svc.endpoint_allowed(body.endpoint):
        raise AppError("This browser's push service isn't supported.", code="push_endpoint_invalid",
                       status_code=422)
    await push_svc.save_subscription(db, user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh,
                                     auth=body.keys.auth, user_agent=request.headers.get("user-agent"))
    await db.commit()
    return {"ok": True}


@router.delete("/me/push-subscriptions")
async def unsubscribe_push(body: PushEndpointIn, user: CurrentUser, db: DB) -> dict:
    await push_svc.remove_subscription(db, user.id, body.endpoint)
    await db.commit()
    return {"ok": True}


# ── Referrals ──────────────────────────────────────────────────────────────


@router.get("/me/referral")
async def my_referral(user: CurrentUser, db: DB) -> dict:
    data = await referrals.summary(db, user)
    await db.commit()  # the code is made on first visit
    return data


@router.get("/referrals/{code}")
async def referral_inviter(code: str, db: DB) -> dict:
    """Public: who sent this invite link, for the "X invited you" banner."""
    inviter = await referrals.inviter_for_code(db, code)
    if inviter is None or not get_settings().referral_enabled:
        raise NotFound("This invite link isn't valid.")
    s = get_settings()
    return {"username": inviter.username, "display_name": inviter.display_name, "avatar_url": inviter.avatar_url,
            "invitee_credits": s.referral_invitee_credits}
