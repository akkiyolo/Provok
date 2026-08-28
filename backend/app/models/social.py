"""
PROVOK — Social models: follows, interactions, notifications, recommendations.
"""
from __future__ import annotations
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Float, Integer, ForeignKey, Index, Enum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.database.core import Base


class FollowType(str, enum.Enum):
    USER = "USER"
    TOPIC = "TOPIC"
    AI_AGENT = "AI_AGENT"


class InteractionType(str, enum.Enum):
    IMPRESSION = "IMPRESSION"
    OPEN = "OPEN"
    READ = "READ"
    WATCH = "WATCH"
    WATCH_COMPLETION = "WATCH_COMPLETION"
    JOIN_DEBATE = "JOIN_DEBATE"
    PARTICIPATE = "PARTICIPATE"
    ARGUMENT_SUBMITTED = "ARGUMENT_SUBMITTED"
    VOTE = "VOTE"
    REACTION = "REACTION"
    CHALLENGE = "CHALLENGE"
    SAVE = "SAVE"
    SHARE = "SHARE"
    FOLLOW = "FOLLOW"
    RETURN = "RETURN"
    DEBATE_COMPLETED = "DEBATE_COMPLETED"
    VERDICT_VIEWED = "VERDICT_VIEWED"
    POSITION_CHANGED = "POSITION_CHANGED"


class Follow(Base):
    __tablename__ = "follows"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    follower_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    follow_type: Mapped[FollowType] = mapped_column(Enum(FollowType), nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    target_topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("uq_follow_user_target", "follower_id", "follow_type", "target_user_id", "target_topic_id", unique=True),
    )


class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_type: Mapped[InteractionType] = mapped_column(Enum(InteractionType), nullable=False)
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="SET NULL"))
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"))
    argument_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id", ondelete="SET NULL"))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="SET NULL"))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
