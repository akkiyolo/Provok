from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, created_at_col, uuid_pk
from backend.app.engine.types import UserRole, UserStatus, values


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    bio: Mapped[str | None] = mapped_column(String(280))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.USER, server_default=UserRole.USER)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=UserStatus.ACTIVE,
                                        server_default=UserStatus.ACTIVE)
    # Bumped on password change / ban / logout-everywhere: invalidates outstanding access tokens.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=1200, server_default="1200")
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    free_ai_debates_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    video_minutes_used_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    video_minutes_period: Mapped[str | None] = mapped_column(String(7))  # "YYYY-MM"
    injection_strikes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    onboarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Challenge, turn and verdict emails. Account emails (verification, password reset) always send.
    email_notifications: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_users_email_lower", func.lower(email), unique=True),
        Index("uq_users_username_lower", func.lower(username), unique=True),
        Index("ix_users_rating", "rating"),
        CheckConstraint("credits >= 0", name="credits_non_negative"),
        CheckConstraint("free_ai_debates_used >= 0", name="free_used_non_negative"),
        CheckConstraint(f"role IN ({values(UserRole)})", name="role_valid"),
        CheckConstraint(f"status IN ({values(UserStatus)})", name="status_valid"),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("uq_oauth_provider_user", "provider", "provider_user_id", unique=True),)


class AuthSession(Base):
    """A refresh-token lineage. Each refresh rotates the token; reuse of a rotated
    token revokes the whole family (stolen-token detection)."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip: Mapped[str | None] = mapped_column(String(64))


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # verify | reset
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("purpose IN ('verify', 'reset')", name="purpose_valid"),)

