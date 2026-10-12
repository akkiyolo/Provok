"""Posts, reactions, feeds, media uploads, hashtags, trends, blocks and mutes."""
from __future__ import annotations

import io
import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.app.api.deps import DB, ActiveDebater, CurrentUser, OptionalUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Forbidden, NotFound
from backend.app.core.ratelimit import enforce
from backend.app.engine.types import UserStatus
from backend.app.models import Post, PostMedia, User
from backend.app.models.social import POST_MAX_CHARS, POST_MAX_MEDIA
from backend.app.services import posts as svc
from backend.app.services import storage
from backend.app.services.outbox import Outbox
from backend.app.workers.queue import enqueue

router = APIRouter()


def _parse_id(post_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(post_id)
    except ValueError as exc:
        raise NotFound("This post isn't available.") from exc


async def _view(db, post: Post, viewer: User | None) -> dict:
    views = await svc.build_views(db, [post], viewer)
    if not views:
        raise NotFound("This post isn't available.")
    return views[0]


# ── Posts ──────────────────────────────────────────────────────────────────


class PostIn(BaseModel):
    text: str | None = Field(default=None, max_length=POST_MAX_CHARS * 2)  # cleaned and re-checked server-side
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=POST_MAX_MEDIA)
    reply_to_id: uuid.UUID | None = None
    quote_of_id: uuid.UUID | None = None


@router.post("/posts", status_code=201)
async def create_post(body: PostIn, user: ActiveDebater, db: DB) -> dict:
    s = get_settings()
    await enforce("post", str(user.id), s.rl_post_user, "You're posting very fast. Take a breath and try again soon.")
    await enforce("post_day", str(user.id), s.rl_post_user_day)
    outbox = Outbox()
    post = await svc.create_post(db, outbox, user, text=body.text, media_ids=body.media_ids,
                                 reply_to_id=body.reply_to_id, quote_of_id=body.quote_of_id)
    await db.commit()
    await outbox.flush()
    if post.text:
        await enqueue("moderate_post", str(post.id), job_id=f"modpost:{post.id}")
    return await _view(db, post, user)


@router.get("/posts/{post_id}")
async def get_post(post_id: str, db: DB, viewer: OptionalUser) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    chain = await svc.ancestors(db, post, viewer)
    return {"post": await _view(db, post, viewer), "ancestors": await svc.build_views(db, chain, viewer)}


@router.get("/posts/{post_id}/replies")
async def get_replies(post_id: str, db: DB, viewer: OptionalUser, cursor: str | None = Query(default=None)) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    rows, nxt = await svc.replies(db, post, viewer, cursor)
    return {"items": await svc.build_views(db, rows, viewer), "next_cursor": nxt}


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str, user: CurrentUser, db: DB) -> dict:
    post = await db.get(Post, _parse_id(post_id))
    if post is None or post.status == "deleted":
        raise NotFound("This post isn't available.")
    if post.author_id != user.id and user.role != "admin":
        raise Forbidden("You can only delete your own posts.")
    await svc.delete_post(db, post)
    await db.commit()
    return {"ok": True}


# ── Reactions ──────────────────────────────────────────────────────────────


async def _react(kind: Literal["like", "repost", "bookmark"], post_id: str, user: User, db, on: bool) -> dict:
    await enforce("reaction", str(user.id), get_settings().rl_reaction_user)
    pid = _parse_id(post_id)
    outbox = Outbox()
    if kind == "like":
        target = await svc.set_like(db, outbox, user, pid, on)
    elif kind == "repost":
        target = await svc.set_repost(db, outbox, user, pid, on)
    else:
        await svc.set_bookmark(db, user, pid, on)
        target = await svc.get_visible_post(db, pid, user.id)
    await db.commit()
    await outbox.flush()
    return await _view(db, target, user)


@router.post("/posts/{post_id}/like")
async def like(post_id: str, user: ActiveDebater, db: DB) -> dict:
    return await _react("like", post_id, user, db, True)


@router.delete("/posts/{post_id}/like")
async def unlike(post_id: str, user: CurrentUser, db: DB) -> dict:
    return await _react("like", post_id, user, db, False)


@router.post("/posts/{post_id}/repost")
async def repost(post_id: str, user: ActiveDebater, db: DB) -> dict:
    return await _react("repost", post_id, user, db, True)


@router.delete("/posts/{post_id}/repost")
async def unrepost(post_id: str, user: CurrentUser, db: DB) -> dict:
    return await _react("repost", post_id, user, db, False)


@router.post("/posts/{post_id}/bookmark")
async def bookmark(post_id: str, user: CurrentUser, db: DB) -> dict:
    return await _react("bookmark", post_id, user, db, True)


@router.delete("/posts/{post_id}/bookmark")
async def unbookmark(post_id: str, user: CurrentUser, db: DB) -> dict:
    return await _react("bookmark", post_id, user, db, False)


# ── Feeds ──────────────────────────────────────────────────────────────────


@router.get("/feed")
async def feed(db: DB, viewer: OptionalUser, tab: Literal["for_you", "following"] = "for_you",
               cursor: str | None = Query(default=None, max_length=200)) -> dict:
    if tab == "following":
        if viewer is None:
            return {"items": [], "next_cursor": None}
        rows, nxt = await svc.following_feed(db, viewer, cursor)
    else:
        page = int(cursor) if cursor and cursor.isdigit() else 0
        rows, nxt = await svc.for_you_feed(db, viewer, page)
    return {"items": await svc.build_views(db, rows, viewer), "next_cursor": nxt}


@router.get("/users/{username}/posts")
async def posts_by_user(username: str, db: DB, viewer: OptionalUser,
                        tab: Literal["posts", "replies", "media", "likes"] = "posts",
                        cursor: str | None = Query(default=None, max_length=200)) -> dict:
    author = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if author is None or author.status in (UserStatus.DELETED, UserStatus.BANNED):
        raise NotFound("User not found.")
    if viewer and author.id in await svc.blocked_either_way(db, viewer.id):
        return {"items": [], "next_cursor": None, "blocked": True}
    rows, nxt = await svc.user_posts(db, author, viewer, tab, cursor)
    return {"items": await svc.build_views(db, rows, viewer), "next_cursor": nxt}


@router.get("/me/bookmarks")
async def my_bookmarks(user: CurrentUser, db: DB, cursor: str | None = Query(default=None, max_length=200)) -> dict:
    rows, nxt = await svc.bookmarks(db, user, cursor)
    return {"items": await svc.build_views(db, rows, user), "next_cursor": nxt}


@router.get("/tags/{tag}")
async def tag(tag: str, db: DB, viewer: OptionalUser, cursor: str | None = Query(default=None, max_length=200)) -> dict:
    rows, nxt = await svc.tag_feed(db, tag[:64], viewer, cursor)
    return {"tag": tag.lower()[:64], "items": await svc.build_views(db, rows, viewer), "next_cursor": nxt}


@router.get("/trends")
async def trends(db: DB) -> dict:
    return {"items": await svc.trends(db)}


# ── Media ──────────────────────────────────────────────────────────────────

MAX_MEDIA_EDGE = 2048
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


@router.post("/media", status_code=201)
async def upload_media(user: ActiveDebater, db: DB, file: UploadFile = File(...),
                       alt: str | None = Query(default=None, max_length=1000)) -> dict:
    s = get_settings()
    await enforce("media", str(user.id), s.rl_media_user)
    data = await file.read(s.max_upload_bytes + 1)
    if len(data) > s.max_upload_bytes:
        raise AppError("Images must be under 5 MB.", code="file_too_large", status_code=413)
    from PIL import Image, ImageOps, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_IMAGE_FORMATS:
            raise AppError("Upload a JPEG, PNG, WebP or GIF.", code="bad_image", status_code=415)
        img.seek(0)
        img = ImageOps.exif_transpose(img).convert("RGB")  # honour phone rotation before EXIF is dropped
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise AppError("That file isn't a valid image.", code="bad_image", status_code=415) from exc
    img.thumbnail((MAX_MEDIA_EDGE, MAX_MEDIA_EDGE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=82)  # re-encode: strips metadata (EXIF/GPS) and any embedded payloads
    key = f"posts/{user.id}/{secrets.token_hex(12)}.webp"
    url = await storage.put_bytes(key, out.getvalue(), "image/webp")
    m = PostMedia(owner_id=user.id, storage_key=key, url=url, width=img.width, height=img.height,
                  alt=(alt or "").strip() or None)
    db.add(m)
    await db.commit()
    return {"id": str(m.id), "url": url, "width": m.width, "height": m.height}


# ── Blocks and mutes ───────────────────────────────────────────────────────


async def _target(db, username: str) -> User:
    target = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if target is None or target.status == UserStatus.DELETED:
        raise NotFound("User not found.")
    return target


@router.post("/users/{username}/block")
async def block(username: str, user: CurrentUser, db: DB) -> dict:
    await svc.set_block(db, user, await _target(db, username), True)
    await db.commit()
    return {"blocked": True}


@router.delete("/users/{username}/block")
async def unblock(username: str, user: CurrentUser, db: DB) -> dict:
    await svc.set_block(db, user, await _target(db, username), False)
    await db.commit()
    return {"blocked": False}


@router.post("/users/{username}/mute")
async def mute(username: str, user: CurrentUser, db: DB) -> dict:
    await svc.set_mute(db, user, await _target(db, username), True)
    await db.commit()
    return {"muted": True}


@router.delete("/users/{username}/mute")
async def unmute(username: str, user: CurrentUser, db: DB) -> dict:
    await svc.set_mute(db, user, await _target(db, username), False)
    await db.commit()
    return {"muted": False}
