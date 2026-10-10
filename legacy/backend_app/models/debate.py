"""
PROVOK — Debate domain models.

Core tables: questions, topics, debates, sides, participants,
rounds, turns, messages, arguments, claims, evidence, votes,
audience_challenges, verdicts, position_history.
"""
from __future__ import annotations
import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    String, Text, Boolean, DateTime, Float, Integer,
    ForeignKey, Index, Enum, func, CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database.core import Base


# ── Enums ──────────────────────────────────────────────────────

class DebateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    LIVE = "LIVE"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class DebateMode(str, enum.Enum):
    LIVE = "LIVE"
    ASYNC = "ASYNC"

class DebateType(str, enum.Enum):
    HUMAN_VS_HUMAN = "HUMAN_VS_HUMAN"
    HUMAN_VS_AI = "HUMAN_VS_AI"
    AI_VS_AI = "AI_VS_AI"

class DebateVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"

class RoundPhase(str, enum.Enum):
    OPENING = "OPENING"
    REBUTTAL = "REBUTTAL"
    CROSS_EXAMINATION = "CROSS_EXAMINATION"
    CLOSING = "CLOSING"

class RoundStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    VOTING = "VOTING"
    COMPLETED = "COMPLETED"

class TurnStatus(str, enum.Enum):
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"
    EXPIRED = "EXPIRED"
    SKIPPED = "SKIPPED"

class ParticipantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    AWAY = "AWAY"
    OFFLINE = "OFFLINE"
    RETURNED = "RETURNED"
    CONCEDED = "CONCEDED"
    FORFEITED = "FORFEITED"

class ParticipantType(str, enum.Enum):
    HUMAN = "HUMAN"
    AI_SWARM = "AI_SWARM"

class ArgumentType(str, enum.Enum):
    OPENING = "OPENING"
    REBUTTAL = "REBUTTAL"
    QUESTION = "QUESTION"
    ANSWER = "ANSWER"
    CLOSING = "CLOSING"
    CONCESSION = "CONCESSION"

class ClaimStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    CONTESTED = "CONTESTED"
    REFUTED = "REFUTED"
    UNRESOLVED = "UNRESOLVED"
    CONCEDED = "CONCEDED"

class CompletionReason(str, enum.Enum):
    BOTH_FINISHED = "BOTH_FINISHED"
    MAX_CONTRIBUTIONS = "MAX_CONTRIBUTIONS"
    TIMEOUT = "TIMEOUT"
    CONCESSION = "CONCESSION"
    FORFEIT = "FORFEIT"
    EARLY_CONVERGENCE = "EARLY_CONVERGENCE"
    TECHNICAL_TERMINATION = "TECHNICAL_TERMINATION"

class SideLabel(str, enum.Enum):
    FOR = "FOR"
    AGAINST = "AGAINST"


# ── Topics ─────────────────────────────────────────────────────

class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Questions ──────────────────────────────────────────────────

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    debates: Mapped[list["Debate"]] = relationship(back_populates="question")


class QuestionTopic(Base):
    __tablename__ = "question_topics"
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)


# ── Debates ────────────────────────────────────────────────────

class Debate(Base):
    __tablename__ = "debates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    debate_type: Mapped[DebateType] = mapped_column(Enum(DebateType), nullable=False)
    mode: Mapped[DebateMode] = mapped_column(Enum(DebateMode), nullable=False)
    visibility: Mapped[DebateVisibility] = mapped_column(Enum(DebateVisibility), default=DebateVisibility.PUBLIC)
    status: Mapped[DebateStatus] = mapped_column(Enum(DebateStatus), default=DebateStatus.DRAFT, index=True)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=4)
    completion_reason: Mapped[CompletionReason | None] = mapped_column(Enum(CompletionReason))
    async_response_hours: Mapped[int | None] = mapped_column(Integer)
    viewer_count: Mapped[int] = mapped_column(Integer, default=0)
    invite_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    objective: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    question: Mapped["Question"] = relationship(back_populates="debates")
    sides: Mapped[list["DebateSide"]] = relationship(back_populates="debate", cascade="all, delete-orphan")
    participants: Mapped[list["Participant"]] = relationship(back_populates="debate", cascade="all, delete-orphan")
    rounds: Mapped[list["Round"]] = relationship(back_populates="debate", cascade="all, delete-orphan", order_by="Round.round_number")

    @property
    def title(self) -> str:
        return self.question.text if self.question else "Debate"

    @property
    def creator_id(self) -> uuid.UUID | None:
        # Default to first human participant
        for p in self.participants:
            if p.participant_type == ParticipantType.HUMAN:
                return p.user_id
        return None


class DebateSide(Base):
    __tablename__ = "debate_sides"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[SideLabel] = mapped_column(Enum(SideLabel), nullable=False)
    position: Mapped[str] = mapped_column(Text, nullable=False)
    debate: Mapped["Debate"] = relationship(back_populates="sides")
    __table_args__ = (Index("uq_debate_side_label", "debate_id", "label", unique=True),)


class Participant(Base):
    __tablename__ = "participants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_sides.id"), nullable=False)
    participant_type: Mapped[ParticipantType] = mapped_column(Enum(ParticipantType), nullable=False)
    status: Mapped[ParticipantStatus] = mapped_column(Enum(ParticipantStatus), default=ParticipantStatus.ACTIVE)
    initial_position: Mapped[str | None] = mapped_column(String(50))
    initial_confidence: Mapped[float | None] = mapped_column(Float)
    final_position: Mapped[str | None] = mapped_column(String(50))
    final_confidence: Mapped[float | None] = mapped_column(Float)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    debate: Mapped["Debate"] = relationship(back_populates="participants")
    user: Mapped["User | None"] = relationship()
    __table_args__ = (Index("uq_debate_participant", "debate_id", "user_id", unique=True),)


# ── Rounds ─────────────────────────────────────────────────────

class Round(Base):
    __tablename__ = "rounds"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[RoundPhase] = mapped_column(Enum(RoundPhase), nullable=False)
    status: Mapped[RoundStatus] = mapped_column(Enum(RoundStatus), default=RoundStatus.PENDING)
    completion_reason: Mapped[CompletionReason | None] = mapped_column(Enum(CompletionReason))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voting_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voting_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    debate: Mapped["Debate"] = relationship(back_populates="rounds")
    turns: Mapped[list["Turn"]] = relationship(back_populates="round", cascade="all, delete-orphan")
    arguments: Mapped[list["Argument"]] = relationship(back_populates="round", cascade="all, delete-orphan")
    __table_args__ = (Index("uq_debate_round", "debate_id", "round_number", unique=True),)


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TurnStatus] = mapped_column(Enum(TurnStatus), default=TurnStatus.WAITING)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    round: Mapped["Round"] = relationship(back_populates="turns")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rounds.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Arguments ──────────────────────────────────────────────────

class Argument(Base):
    __tablename__ = "arguments"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False, index=True)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("participants.id"), nullable=False)
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_sides.id"), nullable=False)
    argument_type: Mapped[ArgumentType] = mapped_column(Enum(ArgumentType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    round: Mapped["Round"] = relationship(back_populates="arguments")
    claims: Mapped[list["Claim"]] = relationship(back_populates="argument", cascade="all, delete-orphan")
    evidence_links: Mapped[list["ArgumentEvidence"]] = relationship(back_populates="argument", cascade="all, delete-orphan")


# ── Claims ─────────────────────────────────────────────────────

class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    argument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id", ondelete="CASCADE"), nullable=False)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.UNRESOLVED)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    argument: Mapped["Argument"] = relationship(back_populates="claims")


# ── Evidence ───────────────────────────────────────────────────

class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(1000))
    publication_date: Mapped[str | None] = mapped_column(String(50))
    excerpt: Mapped[str | None] = mapped_column(Text)
    credibility: Mapped[float | None] = mapped_column(Float)
    relevance: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArgumentEvidence(Base):
    __tablename__ = "argument_evidence"
    argument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id", ondelete="CASCADE"), primary_key=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="CASCADE"), primary_key=True)
    argument: Mapped["Argument"] = relationship(back_populates="evidence_links")


# ── Votes ──────────────────────────────────────────────────────

class Vote(Base):
    __tablename__ = "votes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    argument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("uq_vote_user_argument", "user_id", "argument_id", unique=True),)


class RoundVote(Base):
    __tablename__ = "round_votes"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    side_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_sides.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("uq_round_vote_user", "round_id", "user_id", unique=True),)


class AudienceChallenge(Base):
    __tablename__ = "audience_challenges"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    round_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ── Verdicts ───────────────────────────────────────────────────

class Verdict(Base):
    __tablename__ = "verdicts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), unique=True, nullable=False)
    audience_winner_side_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_sides.id"))
    evidence_advantage_side_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("debate_sides.id"))
    judge_conclusion: Mapped[str | None] = mapped_column(String(100))
    judge_confidence: Mapped[float | None] = mapped_column(Float)
    evidence_quality_a: Mapped[float | None] = mapped_column(Float)
    evidence_quality_b: Mapped[float | None] = mapped_column(Float)
    reasoning_a: Mapped[float | None] = mapped_column(Float)
    reasoning_b: Mapped[float | None] = mapped_column(Float)
    rebuttal_effectiveness_a: Mapped[float | None] = mapped_column(Float)
    rebuttal_effectiveness_b: Mapped[float | None] = mapped_column(Float)
    consistency_a: Mapped[float | None] = mapped_column(Float)
    consistency_b: Mapped[float | None] = mapped_column(Float)
    responsiveness_a: Mapped[float | None] = mapped_column(Float)
    responsiveness_b: Mapped[float | None] = mapped_column(Float)
    strongest_argument_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id"))
    strongest_rebuttal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("arguments.id"))
    synthesis: Mapped[str | None] = mapped_column(Text)
    areas_of_agreement: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositionHistory(Base):
    __tablename__ = "position_history"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    debate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("debates.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    phase: Mapped[str] = mapped_column(String(20), nullable=False)  # "BEFORE" or "AFTER"
