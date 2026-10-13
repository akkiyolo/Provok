"""The social layer: posts (with replies, quotes and reposts), media, likes, bookmarks, hashtags, blocks, mutes."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, created_at_col, uuid_pk

POST_MAX_CHARS = 500
POST_MAX_MEDIA = 4


class Post(Base):
    """A post, reply, quote or repost.

    A repost is its own row (kind='repost', no text) pointing at the original, so it can appear in timelines at
    the time it was reposted. Replies keep `root_id` (the thread's first post) for whole-thread reads.
    """
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = uuid_pk()
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                 nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="post", server_default="post")
    text: Mapped[str | None] = mapped_column(String(POST_MAX_CHARS))
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         ForeignKey("posts.id", ondelete="SET NULL"))
    root_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="SET NULL"))
    quote_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                         ForeignKey("posts.id", ondelete="SET NULL"))
    repost_of_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                          ForeignKey("posts.id", ondelete="CASCADE"))
    # visible | hidden (moderation) | deleted (by the author or with the account)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="visible", server_default="visible")
    moderation_reason: Mapped[str | None] = mapped_column(String(200))
    lang: Mapped[str | None] = mapped_column(String(8))  # detected from the script: en, hi, bn, ta, ...
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    repost_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    quote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # {"url", "title", "description", "image", "site"} for the first link, fetched after posting.
    link_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("kind IN ('post', 'repost')", name="kind_valid"),
        CheckConstraint("status IN ('visible', 'hidden', 'deleted')", name="status_valid"),
        CheckConstraint("(kind = 'repost') = (repost_of_id IS NOT NULL)", name="repost_has_target"),
        CheckConstraint("kind = 'post' OR (text IS NULL AND reply_to_id IS NULL AND quote_of_id IS NULL)",
                        name="repost_is_bare"),
        CheckConstraint(f"text IS NULL OR char_length(text) <= {POST_MAX_CHARS}", name="text_length"),
        CheckConstraint("reply_count >= 0 AND repost_count >= 0 AND quote_count >= 0 AND like_count >= 0",
                        name="counts_non_negative"),
        Index("ix_posts_author_created", "author_id", "created_at"),
        Index("ix_posts_reply_to_created", "reply_to_id", "created_at"),
        Index("ix_posts_root_created", "root_id", "created_at"),
        Index("ix_posts_created", "created_at"),
        # One live repost per user per post.
        Index("uq_posts_one_repost", "author_id", "repost_of_id", unique=True,
              postgresql_where=sql_text("repost_of_id IS NOT NULL AND status <> 'deleted'")),
    )


class PostMedia(Base):
    """An uploaded image. Created unattached by the upload endpoint, then claimed by the post that uses it."""
    __tablename__ = "post_media"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                nullable=False)
    post_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                                     index=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    alt: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_post_media_owner_unattached", "owner_id", "created_at",
                            postgresql_where=sql_text("post_id IS NULL")),)


class PostLike(Base):
    __tablename__ = "post_likes"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_post_likes_post", "post_id"), Index("ix_post_likes_user_created", "user_id", "created_at"))


class Bookmark(Base):
    __tablename__ = "bookmarks"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_bookmarks_user_created", "user_id", "created_at"),)


class PostHashtag(Base):
    __tablename__ = "post_hashtags"

    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)  # lower-case, without '#'
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_post_hashtags_tag_created", "tag", "created_at"),)


class UserBlock(Base):
    """The blocked user can't follow, reply to, quote, mention or see the blocker's posts in feeds (and vice versa)."""
    __tablename__ = "user_blocks"

    blocker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                  primary_key=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                  primary_key=True, index=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),)


class UserMute(Base):
    """Silently hides the muted user's posts and notifications from the muter. The muted user isn't told."""
    __tablename__ = "user_mutes"

    muter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                primary_key=True)
    muted_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                primary_key=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("muter_id <> muted_id", name="no_self_mute"),)



class PostTranslation(Base):
    """Machine translations, made once on first request and then served from here."""
    __tablename__ = "post_translations"

    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    lang: Mapped[str] = mapped_column(String(8), primary_key=True)
    text: Mapped[str] = mapped_column(String(POST_MAX_CHARS * 3), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class PostFactCheck(Base):
    """An AI fact-check of a post's claims against web sources, requested by a reader and shared with everyone."""
    __tablename__ = "post_factchecks"

    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    # pending | done | opinion (nothing factual to check) | failed
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="pending", server_default="pending")
    # accurate | mostly_accurate | missing_context | misleading | false | unverifiable
    rating: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(String(600))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                          ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'opinion', 'failed')", name="status_valid"),
        CheckConstraint("rating IS NULL OR rating IN ('accurate', 'mostly_accurate', 'missing_context', 'misleading', "
                        "'false', 'unverifiable')", name="rating_valid"),
    )


POLL_MIN_OPTIONS, POLL_MAX_OPTIONS, POLL_OPTION_MAX_CHARS = 2, 4, 40


class PostPoll(Base):
    __tablename__ = "post_polls"

    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"),
                                               primary_key=True)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class PollVote(Base):
    """One vote per person per poll; final once cast (as on X)."""
    __tablename__ = "poll_votes"

    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("post_polls.post_id", ondelete="CASCADE"),
                                               primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    option: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint(f"option >= 0 AND option < {POLL_MAX_OPTIONS}", name="option_range"),)


class DailyDebate(Base):
    """One question a day: an official post with a Yes/No poll, plus an AI-vs-AI debate on it."""
    __tablename__ = "daily_debates"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    question: Mapped[str] = mapped_column(String(400), nullable=False)
    post_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("posts.id", ondelete="SET NULL"))
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                       ForeignKey("debates.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = created_at_col()


# ── Direct messages ────────────────────────────────────────────────────────


class Conversation(Base):
    """A one-to-one conversation. The pair is stored ordered (user_a < user_b) so it's unique either way round."""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_a: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                              nullable=False)
    user_b: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                              nullable=False)
    a_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    b_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("user_a < user_b", name="ordered_pair"),
        UniqueConstraint("user_a", "user_b", name="uq_conversations_pair"),
        Index("ix_conversations_a_last", "user_a", "last_message_at"),
        Index("ix_conversations_b_last", "user_b", "last_message_at"),
    )


DM_MAX_CHARS = 1000


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                                                       ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                 nullable=False)
    text: Mapped[str] = mapped_column(String(DM_MAX_CHARS), nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_direct_messages_conversation_created", "conversation_id", "created_at"),)
