from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, created_at_col, uuid_pk
from backend.app.engine.types import (
    ClaimStatus,
    Mode,
    ModerationStatus,
    ParticipantType,
    Position,
    Round,
    Status,
    Timing,
    TurnKind,
    TurnSource,
    values,
)


class Debate(Base):
    __tablename__ = "debates"

    id: Mapped[uuid.UUID] = uuid_pk()
    question: Mapped[str] = mapped_column(Text, nullable=False)
    topic_category: Mapped[str] = mapped_column(String(40), nullable=False, default="general")
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    timing: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_round: Mapped[str | None] = mapped_column(String(16))
    current_turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    swarm_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    paused_reason: Mapped[str | None] = mapped_column(String(200))
    paused_from: Mapped[str | None] = mapped_column(String(32))
    conceded_position: Mapped[str | None] = mapped_column(String(8))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                                                       index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    word_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=200, server_default="200")
    # Monetisation snapshot (what the creator paid, so refunds are exact).
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    paid_with: Mapped[str] = mapped_column(String(8), nullable=False, default="none", server_default="none")
    refunded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = created_at_col()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)

    sides: Mapped[list[Side]] = relationship(back_populates="debate", cascade="all, delete-orphan",
                                             order_by="Side.position.desc()", lazy="selectin")

    __table_args__ = (
        CheckConstraint(f"mode IN ({values(Mode)})", name="mode_valid"),
        CheckConstraint(f"timing IN ({values(Timing)})", name="timing_valid"),
        CheckConstraint(f"status IN ({values(Status)})", name="status_valid"),
        CheckConstraint(f"current_round IS NULL OR current_round IN ({values(Round)})", name="round_valid"),
        CheckConstraint("word_limit BETWEEN 20 AND 2000", name="word_limit_range"),
        CheckConstraint("paid_with IN ('none', 'free', 'credits')", name="paid_with_valid"),
        CheckConstraint(f"paused_from IS NULL OR paused_from IN ({values(Status)})", name="paused_from_valid"),
        Index("ix_debates_status_created", "status", "created_at"),
        Index("ix_debates_deadline_active", "deadline_at", postgresql_where=text("deadline_at IS NOT NULL")),
        Index("ix_debates_featured", "is_featured", postgresql_where=text("is_featured")),
    )

    def side(self, position: Position | str) -> Side:
        for s in self.sides:
            if s.position == position:
                return s
        raise KeyError(position)


class Side(Base):
    __tablename__ = "sides"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    participant_type: Mapped[str | None] = mapped_column(String(8))  # NULL = open slot (awaiting opponent)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                                                      index=True)
    # {"model_key": "claude_opus", "persona": "data_driven"}
    swarm_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # "Challenge someone": only this user may take the open slot.
    invited_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                              ForeignKey("users.id", ondelete="SET NULL"))
    # "Invite link": only someone holding this token (shared privately, e.g. on WhatsApp) may take the open slot.
    invite_token: Mapped[str | None] = mapped_column(String(64))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    debate: Mapped[Debate] = relationship(back_populates="sides")

    __table_args__ = (
        UniqueConstraint("debate_id", "position", name="uq_sides_debate_position"),
        Index("uq_sides_debate_user", "debate_id", "user_id", unique=True,
              postgresql_where=text("user_id IS NOT NULL")),
        CheckConstraint(f"position IN ({values(Position)})", name="position_valid"),
        CheckConstraint(f"participant_type IS NULL OR participant_type IN ({values(ParticipantType)})",
                        name="participant_type_valid"),
        CheckConstraint(
            "(participant_type = 'swarm' AND swarm_config IS NOT NULL AND user_id IS NULL) OR "
            "(participant_type = 'human') OR participant_type IS NULL",
            name="swarm_has_config",
        ),
    )

    @property
    def is_swarm(self) -> bool:
        return self.participant_type == ParticipantType.SWARM


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    round: Mapped[str] = mapped_column(String(16), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sides.id", ondelete="CASCADE"),
                                               nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False)
    model_key: Mapped[str | None] = mapped_column(String(64))
    citations: Mapped[list[Any] | None] = mapped_column(JSONB)  # [{"n": 1, "url": ..., "title": ...}]
    is_forfeit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    moderation_status: Mapped[str] = mapped_column(String(12), nullable=False, default=ModerationStatus.UNCHECKED,
                                                   server_default=ModerationStatus.UNCHECKED)
    moderation_reason: Mapped[str | None] = mapped_column(String(200))
    injection_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    # Video: caption segments [{"start_ms", "end_ms", "text"}] and offsets into the recording (for clips).
    segments: Mapped[list[Any] | None] = mapped_column(JSONB)
    started_ms: Mapped[int | None] = mapped_column(Integer)
    ended_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("debate_id", "round", "turn_index", name="uq_turns_debate_round_index"),
        Index("uq_turns_idempotency", "debate_id", "idempotency_key", unique=True,
              postgresql_where=text("idempotency_key IS NOT NULL")),
        Index("ix_turns_debate_created", "debate_id", "created_at"),
        CheckConstraint(f"round IN ({values(Round)})", name="round_valid"),
        CheckConstraint(f"kind IN ({values(TurnKind)})", name="kind_valid"),
        CheckConstraint(f"source IN ({values(TurnSource)})", name="source_valid"),
        CheckConstraint(f"moderation_status IN ({values(ModerationStatus)})", name="moderation_valid"),
    )


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # human/LLM-friendly id: C1, C2 …
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("turns.id", ondelete="CASCADE"),
                                               nullable=False)
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sides.id", ondelete="CASCADE"),
                                               nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    responds_to_claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                                   ForeignKey("claims.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ClaimStatus.UNADDRESSED,
                                        server_default=ClaimStatus.UNADDRESSED)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("debate_id", "seq", name="uq_claims_debate_seq"),
        CheckConstraint(f"status IN ({values(ClaimStatus)})", name="status_valid"),
    )


class DebateRound(Base):
    """Per-round bookkeeping: timing and the audience vote window/tally."""

    __tablename__ = "debate_rounds"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    round: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vote_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # NULL while open with no fixed close (async: closes when next round ends).
    vote_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vote_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tally: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("debate_id", "round", name="uq_debate_rounds_debate_round"),
        Index("ix_debate_rounds_vote_closes", "vote_closes_at",
              postgresql_where=text("vote_closed_at IS NULL AND vote_closes_at IS NOT NULL")),
    )

    @property
    def vote_open(self) -> bool:
        return self.vote_opened_at is not None and self.vote_closed_at is None


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    round: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False)
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sides.id", ondelete="CASCADE"),
                                               nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("1.00"),
                                            server_default="1.00")
    via_share_link: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("debate_id", "round", "user_id", name="uq_votes_debate_round_user"),
        CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),
    )


class Verdict(Base):
    __tablename__ = "verdicts"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False, unique=True)
    winner_side_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                             ForeignKey("sides.id", ondelete="SET NULL"))
    is_close: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {"for": total, "against": total}
    per_round: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    decisive_claim_ids: Mapped[list[Any] | None] = mapped_column(JSONB)
    judge_runs: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    judge_model_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()


class ResearchCache(Base):
    __tablename__ = "research_cache"

    id: Mapped[uuid.UUID] = uuid_pk()
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"),
                                                 nullable=False)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    facts: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)  # [{id, fact, url, title}]
    queries: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("debate_id", "position", name="uq_research_cache_debate_position"),)

