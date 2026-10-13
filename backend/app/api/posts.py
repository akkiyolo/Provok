"""Posts, reactions, feeds, media uploads, hashtags, trends, blocks and mutes."""
from __future__ import annotations

import io
import secrets
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from backend.app.api.deps import DB, ActiveDebater, CurrentUser, OptionalUser, VerifiedUser
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Forbidden, NotFound
from backend.app.core.ratelimit import client_ip, enforce
from backend.app.core.redis import get_redis
from backend.app.engine.types import UserStatus
from backend.app.models import Debate, Post, PostMedia, User
from backend.app.models.social import POST_MAX_CHARS, POST_MAX_MEDIA
from backend.app.services import post_ai, storage
from backend.app.services import posts as svc
from backend.app.services.debate_view import build_cards, public_user
from backend.app.services.link_preview import first_url
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
    poll: list[str] | None = Field(default=None, max_length=8)
    poll_hours: int | None = Field(default=None, ge=1, le=24 * 7)


@router.post("/posts", status_code=201)
async def create_post(body: PostIn, user: ActiveDebater, db: DB) -> dict:
    s = get_settings()
    await enforce("post", str(user.id), s.rl_post_user, "You're posting very fast. Take a breath and try again soon.")
    await enforce("post_day", str(user.id), s.rl_post_user_day)
    outbox = Outbox()
    post = await svc.create_post(db, outbox, user, text=body.text, media_ids=body.media_ids,
                                 reply_to_id=body.reply_to_id, quote_of_id=body.quote_of_id,
                                 poll=body.poll, poll_hours=body.poll_hours)
    await db.commit()
    await outbox.flush()
    if post.text:
        await enqueue("moderate_post", str(post.id), job_id=f"modpost:{post.id}")
        if first_url(post.text):
            await enqueue("link_preview", str(post.id), job_id=f"preview:{post.id}")
    return await _view(db, post, user)


VIEW_DEDUPE_SECONDS = 3600


async def _count_view(db, post: Post, request: Request, viewer: User | None) -> None:
    """One view per person (or IP when signed out) per post per hour; authors viewing their own posts don't count."""
    if viewer and viewer.id == post.author_id:
        return
    who = str(viewer.id) if viewer else f"ip:{client_ip(request)}"
    try:
        fresh = await get_redis().set(f"pv:{post.id}:{who}", "1", nx=True, ex=VIEW_DEDUPE_SECONDS)
    except Exception:  # Redis trouble must never break reading a post
        return
    if fresh:
        await db.execute(update(Post).where(Post.id == post.id).values(view_count=Post.view_count + 1))
        await db.commit()
        await db.refresh(post)


@router.get("/posts/{post_id}")
async def get_post(post_id: str, request: Request, db: DB, viewer: OptionalUser) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    await _count_view(db, post, request, viewer)
    chain = await svc.ancestors(db, post, viewer)
    return {"post": await _view(db, post, viewer), "ancestors": await svc.build_views(db, chain, viewer)}


@router.get("/posts/{post_id}/replies")
async def get_replies(post_id: str, db: DB, viewer: OptionalUser, cursor: str | None = Query(default=None)) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    rows, nxt = await svc.replies(db, post, viewer, cursor)
    return {"items": await svc.build_views(db, rows, viewer), "next_cursor": nxt}


@router.get("/posts/{post_id}/likes")
async def likers(post_id: str, db: DB, viewer: OptionalUser,
                 cursor: str | None = Query(default=None, max_length=200)) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    users, nxt = await svc.likers(db, post, viewer, cursor)
    return {"items": [public_user(u) for u in users], "next_cursor": nxt}


@router.post("/posts/{post_id}/pin")
async def pin(post_id: str, user: CurrentUser, db: DB) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), user.id)
    if post.author_id != user.id or post.kind != "post":
        raise Forbidden("You can pin only your own posts.")
    user.pinned_post_id = post.id
    await db.commit()
    return await _view(db, post, user)


@router.delete("/posts/{post_id}/pin")
async def unpin(post_id: str, user: CurrentUser, db: DB) -> dict:
    if user.pinned_post_id == _parse_id(post_id):
        user.pinned_post_id = None
        await db.commit()
    return {"pinned": False}


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


# ── AI on posts: Challenge, fact-check, translate ──────────────────────────


@router.post("/posts/{post_id}/challenge-question")
async def challenge_question(post_id: str, user: ActiveDebater, db: DB,
                             mode: Literal["invite", "open"] = "invite") -> dict:
    """Suggest a neutral debate motion and which side the post's author takes. `invite` challenges the author;
    `open` (Poll → Debate) starts an open challenge anyone can take, including from your own post."""
    await enforce("topic_check", str(user.id), get_settings().rl_topic_check_user)
    post = await svc.get_visible_post(db, _parse_id(post_id), user.id)
    if mode == "invite" and post.author_id == user.id:
        raise AppError("You can't challenge your own post. Start a debate instead.", code="self_challenge",
                       status_code=422)
    suggestion = await post_ai.suggest_question(post)
    author = await db.get(User, post.author_id)
    return {**suggestion, "author": author.username if author else None}


class VoteIn(BaseModel):
    option: int = Field(ge=0, le=3)


@router.post("/posts/{post_id}/vote")
async def vote(post_id: str, body: VoteIn, user: ActiveDebater, db: DB) -> dict:
    await enforce("reaction", str(user.id), get_settings().rl_reaction_user)
    post = await svc.vote_poll(db, user, _parse_id(post_id), body.option)
    await db.commit()
    return await _view(db, post, user)


@router.get("/posts/{post_id}/debates")
async def post_debates(post_id: str, db: DB, viewer: OptionalUser) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    rows = list((await db.scalars(select(Debate).where(
        Debate.source_post_id == post.id, Debate.is_hidden.is_(False),
        Debate.status.not_in(["cancelled", "abandoned"])).order_by(Debate.created_at.desc()).limit(20))).all())
    return {"items": await build_cards(db, rows)}


@router.post("/posts/{post_id}/factcheck")
async def factcheck(post_id: str, user: VerifiedUser, db: DB) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), user.id)
    fc, start = await post_ai.request_factcheck(db, post, user.id)
    if start:
        await enforce("factcheck", str(user.id), get_settings().rl_factcheck_user,
                      "You've asked for a lot of fact-checks today. Try again tomorrow.")
    await db.commit()
    if start:
        await enqueue("factcheck_post", str(post.id), job_id=f"factcheck:{post.id}:{int(fc.updated_at.timestamp())}")
    return post_ai.factcheck_view(fc) or {}


@router.get("/posts/{post_id}/factcheck")
async def get_factcheck(post_id: str, db: DB, viewer: OptionalUser) -> dict:
    post = await svc.get_visible_post(db, _parse_id(post_id), viewer.id if viewer else None)
    from backend.app.models import PostFactCheck
    return post_ai.factcheck_view(await db.get(PostFactCheck, post.id)) or {"status": None}


@router.post("/posts/{post_id}/translate")
async def translate(post_id: str, user: CurrentUser, db: DB, to: Literal["en", "hi"] = "en") -> dict:
    await enforce("translate", str(user.id), get_settings().rl_translate_user)
    post = await svc.get_visible_post(db, _parse_id(post_id), user.id)
    out = await post_ai.translate(db, post, to)
    await db.commit()
    return out


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


@router.get("/feed/new")
async def feed_new(user: CurrentUser, db: DB, since: datetime = Query(...)) -> dict:
    """For the "N new posts" banner on the Following timeline."""
    return {"count": await svc.new_posts_count(db, user, since)}


@router.get("/suggestions/people")
async def people(db: DB, viewer: OptionalUser, limit: int = Query(default=6, ge=1, le=20)) -> dict:
    return {"items": await svc.suggested_people(db, viewer, limit)}


@router.get("/explore")
async def explore(db: DB, viewer: OptionalUser) -> dict:
    top, _ = await svc.for_you_feed(db, viewer, 0, limit=10)
    live = list((await db.scalars(select(Debate).where(
        Debate.status.in_(["opening", "rebuttal", "cross_exam", "closing", "lobby"]), Debate.is_hidden.is_(False))
        .order_by(Debate.is_featured.desc(), Debate.created_at.desc()).limit(4))).all())
    return {"trends": await svc.trends(db), "top_posts": await svc.build_views(db, top, viewer),
            "people": await svc.suggested_people(db, viewer, 5), "live_debates": await build_cards(db, live)}


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


@router.get("/daily")
async def daily(db: DB, viewer: OptionalUser) -> dict:
    from backend.app.services.daily import latest_daily
    found = await latest_daily(db)
    if found is None:
        return {"daily": None}
    row, post, debate = found
    return {"daily": {
        "day": row.day, "question": row.question,
        "post": (await svc.build_views(db, [post], viewer) or [None])[0] if post else None,
        "debate": (await build_cards(db, [debate]))[0] if debate else None,
    }}


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
