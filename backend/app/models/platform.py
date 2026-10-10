"""LLM registry/accounting, payments, social, moderation, analytics, ops."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, created_at_col, uuid_pk
from backend.app.engine.types import ModelTier, values

# ── LLM ────────────────────────────────────────────────────────────────────


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    litellm_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # offered in matchup picker
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=1500, server_default="1500")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default="100")
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)

    __table_args__ = (CheckConstraint(f"tier IN ({values(ModelTier)})", name="tier_valid"),)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="SET NULL"),
                                                       index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    model_key: Mapped[str] = mapped_column(String(64), nullable=False)
    litellm_id: Mapped[str] = mapped_column(String(200), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_llm_calls_created", "created_at"),)


# ── Payments / credits ─────────────────────────────────────────────────────


class CreditLedger(Base):
    """Append-only. users.credits is a cached sum of this table, updated in the same transaction."""

    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    ref_id: Mapped[str | None] = mapped_column(String(100))
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # Guarantees each business event (a payment, a debate charge, a refund) books exactly once.
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("reason IN ('purchase', 'debate', 'refund', 'grant', 'adjustment')", name="reason_valid"),
        CheckConstraint("balance_after >= 0", name="balance_non_negative"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                                               index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="razorpay")
    razorpay_order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    pack_id: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)  # whole rupees
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="created")
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_col()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status IN ('created', 'paid', 'failed')", name="status_valid"),)


# ── Social ─────────────────────────────────────────────────────────────────


class Follow(Base):
    __tablename__ = "follows"

    follower_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                   primary_key=True)
    followee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                                   primary_key=True, index=True)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("follower_id <> followee_id", name="no_self_follow"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)


# ── Moderation / admin ─────────────────────────────────────────────────────


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = uuid_pk()
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("reporter_id", "target_type", "target_id", name="uq_reports_reporter_target"),
        CheckConstraint("target_type IN ('debate', 'turn', 'user')", name="target_type_valid"),
        CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="status_valid"),
        Index("ix_reports_status_created", "status", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(16))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    anon_id: Mapped[str | None] = mapped_column(String(64))
    debate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="SET NULL"))
    props: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (Index("ix_analytics_name_created", "name", "created_at"),)


# ── Video ──────────────────────────────────────────────────────────────────


class VideoSession(Base):
    __tablename__ = "video_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False, unique=True)
    livekit_room: Mapped[str] = mapped_column(String(100), nullable=False)
    egress_id: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_key: Mapped[str | None] = mapped_column(String(500))
    recording_url: Mapped[str | None] = mapped_column(String(1000))
    minutes_billed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False, index=True)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (CheckConstraint("end_ms > start_ms", name="range_valid"),)
