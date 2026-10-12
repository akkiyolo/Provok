"""The social layer: creating posts, reactions, visibility (blocks, mutes, moderation), feeds and views.

Timelines are read at request time ("fan-out on read") from indexed Postgres queries. At our scale that is simpler
and correct, with no per-follower write amplification; a Redis fan-out cache can sit in front later without
changing the API.
"""
from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, delete, desc, func, literal, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AppError, NotFound
from backend.app.core.security import utcnow
from backend.app.engine.types import UserStatus
from backend.app.models import (
    Bookmark,
    Follow,
    Post,
    PostHashtag,
    PostLike,
    PostMedia,
    User,
    UserBlock,
    UserMute,
)
from backend.app.models.social import POST_MAX_CHARS, POST_MAX_MEDIA
from backend.app.moderation.content import URL_RE, heuristic_blocked_category
from backend.app.services.debate_view import public_user
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox

PAGE_SIZE = 25
MAX_MENTION_NOTIFICATIONS = 10
MEDIA_CLAIM_WINDOW = timedelta(hours=24)

# Hashtags may be written in Indian scripts: \w misses their combining vowel signs, so the blocks are listed.
_INDIC = "ऀ-෿"
HASHTAG_RE = re.compile(rf"(?<![\w{_INDIC}#&])#([\w{_INDIC}]{{1,64}})")
MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,20})\b")
VISIBLE_AUTHOR_STATUSES = (UserStatus.ACTIVE.value, UserStatus.RESTRICTED.value)


# ── Text ───────────────────────────────────────────────────────────────────


def clean_text(text: str | None) -> str:
    """Trim, normalise line endings and collapse runs of blank lines (keeps intentional line breaks)."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\n{3,}", "\n\n", t)


def hashtags(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in HASHTAG_RE.finditer(text):
        tag = m.group(1).lower()
        if not tag.isdigit():  # "#1" is a number, not a topic
            seen.setdefault(tag, None)
    return list(seen)[:10]


def mentions(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in MENTION_RE.finditer(text):
        seen.setdefault(m.group(1).lower(), None)
    return list(seen)


# ── Cursors ────────────────────────────────────────────────────────────────


def encode_cursor(created_at: datetime, post_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{post_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, pid = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(pid)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppError("Invalid page cursor.", code="bad_cursor") from exc


def _page(rows: list[Post], limit: int) -> tuple[list[Post], str | None]:
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, encode_cursor(rows[-1].created_at, rows[-1].id)
    return rows, None


def _before(cursor: str | None):
    c = decode_cursor(cursor)
    return tuple_(Post.created_at, Post.id) < (c[0], c[1]) if c else literal(True)


# ── Relationships ──────────────────────────────────────────────────────────


async def blocked_either_way(db: AsyncSession, viewer_id: uuid.UUID | None) -> set[uuid.UUID]:
    if viewer_id is None:
        return set()
    rows = await db.execute(select(UserBlock.blocker_id, UserBlock.blocked_id).where(
        or_(UserBlock.blocker_id == viewer_id, UserBlock.blocked_id == viewer_id)))
    return {b if a == viewer_id else a for a, b in rows.all()}


async def hidden_authors(db: AsyncSession, viewer_id: uuid.UUID | None) -> set[uuid.UUID]:
    """Authors whose posts the viewer shouldn't see in feeds: blocked either way, or muted by the viewer."""
    if viewer_id is None:
        return set()
    muted = (await db.scalars(select(UserMute.muted_id).where(UserMute.muter_id == viewer_id))).all()
    return await blocked_either_way(db, viewer_id) | set(muted)


async def is_blocked(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    return bool(await db.scalar(select(UserBlock.blocker_id).where(or_(
        and_(UserBlock.blocker_id == a, UserBlock.blocked_id == b),
        and_(UserBlock.blocker_id == b, UserBlock.blocked_id == a))).limit(1)))


def _visible(hidden: set[uuid.UUID]):
    """Filters for a feed query on Post joined to its author (User)."""
    conds = [Post.status == "visible", User.status.in_(VISIBLE_AUTHOR_STATUSES)]
    if hidden:
        conds.append(Post.author_id.not_in(hidden))
    return and_(*conds)


async def get_visible_post(db: AsyncSession, post_id: uuid.UUID, viewer_id: uuid.UUID | None = None, *,
                           for_update: bool = False) -> Post:
    q = select(Post).join(User, User.id == Post.author_id).where(
        Post.id == post_id, Post.status == "visible", User.status.in_(VISIBLE_AUTHOR_STATUSES))
    if for_update:
        q = q.with_for_update(of=Post, key_share=True)
    post = await db.scalar(q)
    if post is None or (viewer_id and post.author_id in await blocked_either_way(db, viewer_id)):
        raise NotFound("This post isn't available.")
    return post


# ── Creating ───────────────────────────────────────────────────────────────


async def create_post(db: AsyncSession, outbox: Outbox, author: User, *, text: str | None,
                      media_ids: list[uuid.UUID], reply_to_id: uuid.UUID | None,
                      quote_of_id: uuid.UUID | None) -> Post:
    body = clean_text(text)
    if not body and not media_ids:
        raise AppError("Write something or add a photo.", code="empty_post", status_code=422)
    if len(body) > POST_MAX_CHARS:
        raise AppError(f"Posts can be up to {POST_MAX_CHARS} characters.", code="too_long", status_code=422)
    if len(media_ids) > POST_MAX_MEDIA:
        raise AppError(f"Add up to {POST_MAX_MEDIA} photos.", code="too_many_media", status_code=422)
    if body and (category := heuristic_blocked_category(body)):
        raise AppError(f"Posts about {category} aren't allowed on Provok right now.", code="blocked_category",
                       status_code=422, details={"category": category})
    if len(URL_RE.findall(body)) > 4:
        raise AppError("That's a lot of links. Keep it to four.", code="link_spam", status_code=422)

    parent = quoted = None
    if reply_to_id:
        parent = await get_visible_post(db, reply_to_id, author.id, for_update=True)
        if parent.kind == "repost":
            raise AppError("Reply to the original post.", code="reply_to_repost", status_code=422)
    if quote_of_id:
        quoted = await get_visible_post(db, quote_of_id, author.id, for_update=True)
        if quoted.kind == "repost":  # quoting a repost quotes the original
            quoted = await get_visible_post(db, quoted.repost_of_id, author.id, for_update=True)  # type: ignore[arg-type]

    media: list[PostMedia] = []
    if media_ids:
        media = list((await db.scalars(select(PostMedia).where(
            PostMedia.id.in_(media_ids), PostMedia.owner_id == author.id, PostMedia.post_id.is_(None),
            PostMedia.created_at > utcnow() - MEDIA_CLAIM_WINDOW))).all())
        if len(media) != len(set(media_ids)):
            raise AppError("One of the photos is missing or expired. Upload it again.", code="bad_media",
                           status_code=422)

    post = Post(author_id=author.id, kind="post", text=body or None,
                reply_to_id=parent.id if parent else None,
                root_id=(parent.root_id or parent.id) if parent else None,
                quote_of_id=quoted.id if quoted else None)
    db.add(post)
    await db.flush()
    order = {mid: i for i, mid in enumerate(media_ids)}
    for m in media:
        m.post_id, m.position = post.id, order[m.id]
    for tag in hashtags(body):
        db.add(PostHashtag(post_id=post.id, tag=tag))

    link = f"/p/{post.id}"
    who = author.display_name
    if parent:
        parent.reply_count += 1
        await _notify_unless_hidden(db, outbox, parent.author_id, author, "reply", f"{who} replied to you",
                                    body=body[:200], link=link)
    if quoted:
        quoted.quote_count += 1
        await _notify_unless_hidden(db, outbox, quoted.author_id, author, "quote", f"{who} quoted your post",
                                    body=body[:200], link=link)
    already = {p.author_id for p in (parent, quoted) if p}
    if names := mentions(body):
        targets = (await db.scalars(select(User).where(
            func.lower(User.username).in_(names[:MAX_MENTION_NOTIFICATIONS]),
            User.status.in_(VISIBLE_AUTHOR_STATUSES)))).all()
        for target in targets:
            if target.id not in already:
                await _notify_unless_hidden(db, outbox, target.id, author, "mention", f"{who} mentioned you",
                                            body=body[:200], link=link)
    return post


async def _notify_unless_hidden(db: AsyncSession, outbox: Outbox, user_id: uuid.UUID, actor: User, kind: str,
                                title: str, *, body: str | None = None, link: str | None = None) -> None:
    """Notify, except yourself, or someone who blocked/was blocked by or muted the actor."""
    if user_id == actor.id:
        return
    if await is_blocked(db, user_id, actor.id):
        return
    if await db.scalar(select(UserMute.muter_id).where(UserMute.muter_id == user_id,
                                                       UserMute.muted_id == actor.id)):
        return
    await notify(db, outbox, user_id, kind, title, body=body, link=link)


async def delete_post(db: AsyncSession, post: Post) -> None:
    if post.status == "deleted":
        return
    post.status = "deleted"
    counter = None
    if post.kind == "repost":
        counter = (post.repost_of_id, Post.repost_count)
    elif post.reply_to_id:
        counter = (post.reply_to_id, Post.reply_count)
    if counter:
        await db.execute(update(Post).where(Post.id == counter[0], counter[1] > 0).values({counter[1]: counter[1] - 1}))
    if post.quote_of_id:
        await db.execute(update(Post).where(Post.id == post.quote_of_id, Post.quote_count > 0)
                         .values(quote_count=Post.quote_count - 1))


# ── Reactions ──────────────────────────────────────────────────────────────


def _original(post: Post) -> uuid.UUID:
    return post.repost_of_id if post.kind == "repost" and post.repost_of_id else post.id


async def set_like(db: AsyncSession, outbox: Outbox, user: User, post_id: uuid.UUID, on: bool) -> Post:
    post = await get_visible_post(db, post_id, user.id)
    post = await get_visible_post(db, _original(post), user.id)
    if on:
        res = await db.execute(insert(PostLike).values(user_id=user.id, post_id=post.id)
                               .on_conflict_do_nothing().returning(PostLike.post_id))
        if res.scalar() is not None:
            await db.execute(update(Post).where(Post.id == post.id).values(like_count=Post.like_count + 1))
            await _notify_unless_hidden(db, outbox, post.author_id, user, "like", f"{user.display_name} liked your post",
                                        body=(post.text or "")[:200], link=f"/p/{post.id}")
    else:
        res = await db.execute(delete(PostLike).where(PostLike.user_id == user.id, PostLike.post_id == post.id)
                               .returning(PostLike.post_id))
        if res.scalar() is not None:
            await db.execute(update(Post).where(Post.id == post.id, Post.like_count > 0)
                             .values(like_count=Post.like_count - 1))
    await db.refresh(post)
    return post


async def set_repost(db: AsyncSession, outbox: Outbox, user: User, post_id: uuid.UUID, on: bool) -> Post:
    original = await get_visible_post(db, post_id, user.id)
    original = await get_visible_post(db, _original(original), user.id, for_update=True)
    existing = await db.scalar(select(Post).where(Post.author_id == user.id, Post.repost_of_id == original.id,
                                                  Post.status != "deleted"))
    if on and existing is None:
        db.add(Post(author_id=user.id, kind="repost", repost_of_id=original.id))
        original.repost_count += 1
        await db.flush()
        await _notify_unless_hidden(db, outbox, original.author_id, user, "repost",
                                    f"{user.display_name} reposted your post", body=(original.text or "")[:200],
                                    link=f"/p/{original.id}")
    elif not on and existing is not None:
        await delete_post(db, existing)
        await db.flush()
        await db.refresh(original)
    return original


async def set_bookmark(db: AsyncSession, user: User, post_id: uuid.UUID, on: bool) -> None:
    post = await get_visible_post(db, post_id, user.id)
    pid = _original(post)
    if on:
        await db.execute(insert(Bookmark).values(user_id=user.id, post_id=pid).on_conflict_do_nothing())
    else:
        await db.execute(delete(Bookmark).where(Bookmark.user_id == user.id, Bookmark.post_id == pid))


# ── Blocks and mutes ───────────────────────────────────────────────────────


async def set_block(db: AsyncSession, user: User, target: User, on: bool) -> None:
    if target.id == user.id:
        raise AppError("You can't block yourself.", code="self_block")
    if on:
        await db.execute(insert(UserBlock).values(blocker_id=user.id, blocked_id=target.id).on_conflict_do_nothing())
        # Blocking ends the relationship both ways.
        await db.execute(delete(Follow).where(or_(
            and_(Follow.follower_id == user.id, Follow.followee_id == target.id),
            and_(Follow.follower_id == target.id, Follow.followee_id == user.id))))
    else:
        await db.execute(delete(UserBlock).where(UserBlock.blocker_id == user.id, UserBlock.blocked_id == target.id))


async def set_mute(db: AsyncSession, user: User, target: User, on: bool) -> None:
    if target.id == user.id:
        raise AppError("You can't mute yourself.", code="self_mute")
    if on:
        await db.execute(insert(UserMute).values(muter_id=user.id, muted_id=target.id).on_conflict_do_nothing())
    else:
        await db.execute(delete(UserMute).where(UserMute.muter_id == user.id, UserMute.muted_id == target.id))


# ── Feeds ──────────────────────────────────────────────────────────────────


def _feed_base(hidden: set[uuid.UUID]):
    return select(Post).join(User, User.id == Post.author_id).where(_visible(hidden))


async def _drop_dead_reposts(db: AsyncSession, rows: list[Post], hidden: set[uuid.UUID]) -> list[Post]:
    """A repost is shown only while its original is visible to the viewer."""
    ids = {p.repost_of_id for p in rows if p.kind == "repost"}
    if not ids:
        return rows
    alive = set((await db.scalars(_feed_base(hidden).with_only_columns(Post.id).where(Post.id.in_(ids)))).all())
    return [p for p in rows if p.kind != "repost" or p.repost_of_id in alive]


async def following_feed(db: AsyncSession, viewer: User, cursor: str | None, limit: int = PAGE_SIZE):
    hidden = await hidden_authors(db, viewer.id)
    followees = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    rows = list((await db.scalars(
        _feed_base(hidden).where(or_(Post.author_id.in_(followees), Post.author_id == viewer.id),
                                 Post.reply_to_id.is_(None), _before(cursor))
        .order_by(desc(Post.created_at), desc(Post.id)).limit(limit + 1))).all())
    rows, nxt = _page(rows, limit)
    return await _drop_dead_reposts(db, rows, hidden), nxt


FOR_YOU_WINDOW = timedelta(hours=72)
FOR_YOU_MAX_PAGES = 8


async def for_you_feed(db: AsyncSession, viewer: User | None, page: int, limit: int = PAGE_SIZE):
    """Recent original posts ranked by engagement over age (gravity), with a boost for people the viewer follows.
    score = (1 + likes + 2·replies + 1.5·(reposts + quotes)) / (age_hours + 2)^1.5"""
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    age_hours = func.extract("epoch", func.now() - Post.created_at) / 3600.0
    engagement = 1 + Post.like_count + 2 * Post.reply_count + 1.5 * (Post.repost_count + Post.quote_count)
    score = engagement / func.power(age_hours + 2, 1.5)
    if viewer is not None:
        followed = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
        score = score * case((Post.author_id.in_(followed), 1.5), else_=1.0)
    page = max(0, min(page, FOR_YOU_MAX_PAGES - 1))
    rows = list((await db.scalars(
        _feed_base(hidden).where(Post.kind == "post", Post.reply_to_id.is_(None),
                                 Post.created_at > func.now() - FOR_YOU_WINDOW)
        .order_by(desc(score), desc(Post.created_at)).offset(page * limit).limit(limit + 1))).all())
    more = len(rows) > limit and page + 1 < FOR_YOU_MAX_PAGES
    return rows[:limit], (str(page + 1) if more else None)


async def user_posts(db: AsyncSession, author: User, viewer: User | None, tab: str, cursor: str | None,
                     limit: int = PAGE_SIZE):
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    if tab == "likes":
        c = decode_cursor(cursor)
        q = (_feed_base(hidden).join(PostLike, PostLike.post_id == Post.id)
             .where(PostLike.user_id == author.id,
                    tuple_(PostLike.created_at, Post.id) < (c[0], c[1]) if c else literal(True))
             .order_by(desc(PostLike.created_at), desc(Post.id)).limit(limit + 1)
             .add_columns(PostLike.created_at))
        res = (await db.execute(q)).all()
        rows = [r[0] for r in res[:limit]]
        nxt = encode_cursor(res[limit - 1][1], res[limit - 1][0].id) if len(res) > limit else None
        return rows, nxt
    q = _feed_base(hidden).where(Post.author_id == author.id, _before(cursor))
    if tab == "replies":
        q = q.where(Post.reply_to_id.is_not(None))
    elif tab == "media":
        q = q.where(Post.id.in_(select(PostMedia.post_id).where(PostMedia.post_id.is_not(None))))
    else:
        q = q.where(Post.reply_to_id.is_(None))
    rows, nxt = _page(list((await db.scalars(q.order_by(desc(Post.created_at), desc(Post.id))
                                             .limit(limit + 1))).all()), limit)
    return await _drop_dead_reposts(db, rows, hidden), nxt


async def replies(db: AsyncSession, post: Post, viewer: User | None, cursor: str | None, limit: int = PAGE_SIZE):
    """Direct replies, oldest first (conversation order)."""
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    c = decode_cursor(cursor)
    after = tuple_(Post.created_at, Post.id) > (c[0], c[1]) if c else literal(True)
    rows = list((await db.scalars(_feed_base(hidden).where(Post.reply_to_id == post.id, after)
                                  .order_by(Post.created_at, Post.id).limit(limit + 1))).all())
    return _page(rows, limit)


async def ancestors(db: AsyncSession, post: Post, viewer: User | None, depth: int = 10) -> list[Post]:
    """The chain of posts this one replies to, oldest first. Stops at anything the viewer can't see."""
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    chain: list[Post] = []
    current = post
    while current.reply_to_id and len(chain) < depth:
        parent = await db.scalar(_feed_base(hidden).where(Post.id == current.reply_to_id))
        if parent is None:
            break
        chain.append(parent)
        current = parent
    return list(reversed(chain))


async def tag_feed(db: AsyncSession, tag: str, viewer: User | None, cursor: str | None, limit: int = PAGE_SIZE):
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    rows = list((await db.scalars(
        _feed_base(hidden).where(Post.id.in_(select(PostHashtag.post_id).where(PostHashtag.tag == tag.lower())),
                                 _before(cursor))
        .order_by(desc(Post.created_at), desc(Post.id)).limit(limit + 1))).all())
    return _page(rows, limit)


async def bookmarks(db: AsyncSession, user: User, cursor: str | None, limit: int = PAGE_SIZE):
    hidden = await hidden_authors(db, user.id)
    c = decode_cursor(cursor)
    res = (await db.execute(
        _feed_base(hidden).join(Bookmark, Bookmark.post_id == Post.id).add_columns(Bookmark.created_at)
        .where(Bookmark.user_id == user.id,
               tuple_(Bookmark.created_at, Post.id) < (c[0], c[1]) if c else literal(True))
        .order_by(desc(Bookmark.created_at), desc(Post.id)).limit(limit + 1))).all()
    rows = [r[0] for r in res[:limit]]
    nxt = encode_cursor(res[limit - 1][1], res[limit - 1][0].id) if len(res) > limit else None
    return rows, nxt


async def search_posts(db: AsyncSession, term_like: str, viewer: User | None, limit: int = 20) -> list[Post]:
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    return list((await db.scalars(
        _feed_base(hidden).where(Post.kind == "post", Post.text.ilike(term_like, escape="\\"))
        .order_by(desc(Post.created_at)).limit(limit))).all())


TRENDS_WINDOW = timedelta(hours=24)


async def trends(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Hashtags used by the most distinct people in the last day (so one account can't trend a tag alone)."""
    people = func.count(func.distinct(Post.author_id))
    rows = (await db.execute(
        select(PostHashtag.tag, people.label("people"), func.count().label("posts"))
        .join(Post, Post.id == PostHashtag.post_id).join(User, User.id == Post.author_id)
        .where(PostHashtag.created_at > func.now() - TRENDS_WINDOW, Post.status == "visible",
               User.status.in_(VISIBLE_AUTHOR_STATUSES))
        .group_by(PostHashtag.tag).having(people >= 2)
        .order_by(desc(people), desc(func.count())).limit(limit))).all()
    return [{"tag": t, "people": p, "posts": n} for t, p, n in rows]


# ── Views ──────────────────────────────────────────────────────────────────


async def build_views(db: AsyncSession, posts: list[Post], viewer: User | None) -> list[dict[str, Any]]:
    """Serialise posts for the API in a fixed number of queries, whatever the page size."""
    if not posts:
        return []
    hidden = await hidden_authors(db, viewer.id if viewer else None)
    # Reposts render their original; quotes embed the quoted post (one level).
    originals_needed = {p.repost_of_id for p in posts if p.kind == "repost" and p.repost_of_id}
    originals = {p.id: p for p in (await db.scalars(_feed_base(hidden).where(Post.id.in_(originals_needed)))).all()} \
        if originals_needed else {}
    shown = [originals.get(p.repost_of_id, p) if p.kind == "repost" else p for p in posts]  # type: ignore[arg-type]
    quote_ids = {p.quote_of_id for p in shown if p.quote_of_id}
    quotes = {p.id: p for p in (await db.scalars(_feed_base(hidden).where(Post.id.in_(quote_ids)))).all()} \
        if quote_ids else {}
    parent_ids = {p.reply_to_id for p in shown if p.reply_to_id}
    parents = dict((await db.execute(
        select(Post.id, User.username).join(User, User.id == Post.author_id).where(Post.id.in_(parent_ids)))).all()) \
        if parent_ids else {}

    every = {p.id: p for p in [*posts, *shown, *quotes.values()]}
    authors = {u.id: u for u in (await db.scalars(select(User).where(
        User.id.in_({p.author_id for p in every.values()})))).all()}
    media: dict[uuid.UUID, list[PostMedia]] = {}
    for m in (await db.scalars(select(PostMedia).where(PostMedia.post_id.in_(every.keys()))
                               .order_by(PostMedia.position))).all():
        media.setdefault(m.post_id, []).append(m)  # type: ignore[arg-type]
    liked = reposted = saved = set()
    if viewer is not None:
        ids = list(every.keys())
        liked = set((await db.scalars(select(PostLike.post_id).where(
            PostLike.user_id == viewer.id, PostLike.post_id.in_(ids)))).all())
        reposted = set((await db.scalars(select(Post.repost_of_id).where(
            Post.author_id == viewer.id, Post.repost_of_id.in_(ids), Post.status != "deleted"))).all())
        saved = set((await db.scalars(select(Bookmark.post_id).where(
            Bookmark.user_id == viewer.id, Bookmark.post_id.in_(ids)))).all())

    def one(p: Post, *, embed: bool) -> dict[str, Any]:
        v: dict[str, Any] = {
            "id": str(p.id), "author": public_user(authors.get(p.author_id)), "text": p.text,
            "created_at": p.created_at,
            "media": [{"id": str(m.id), "url": m.url, "width": m.width, "height": m.height, "alt": m.alt}
                      for m in media.get(p.id, [])],
            "reply_to": ({"id": str(p.reply_to_id), "username": parents.get(p.reply_to_id)} if p.reply_to_id
                         else None),
            "counts": {"replies": p.reply_count, "reposts": p.repost_count, "quotes": p.quote_count,
                       "likes": p.like_count},
            "viewer": {"liked": p.id in liked, "reposted": p.id in reposted, "bookmarked": p.id in saved,
                       "is_author": bool(viewer and viewer.id == p.author_id)},
        }
        if not embed:
            q = quotes.get(p.quote_of_id) if p.quote_of_id else None
            v["quote"] = one(q, embed=True) if q else ({"unavailable": True} if p.quote_of_id else None)
        return v

    out = []
    for p in posts:
        if p.kind == "repost":
            original = originals.get(p.repost_of_id)  # type: ignore[arg-type]
            if original is None:
                continue
            view = one(original, embed=False)
            view["reposted_by"] = public_user(authors.get(p.author_id))
            view["feed_id"] = str(p.id)
        else:
            view = one(p, embed=False)
            view["reposted_by"] = None
            view["feed_id"] = str(p.id)
        out.append(view)
    return out
