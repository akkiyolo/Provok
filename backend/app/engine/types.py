"""Domain vocabulary shared by the pure engine, models and API."""
from __future__ import annotations

from enum import StrEnum


class Mode(StrEnum):
    HVH = "hvh"  # human vs human
    HVA = "hva"  # human vs AI swarm
    AVA = "ava"  # AI swarm vs AI swarm


class Timing(StrEnum):
    LIVE = "live"
    ASYNC = "async"
    VIDEO = "video"


class Position(StrEnum):
    FOR = "for"
    AGAINST = "against"

    @property
    def other(self) -> Position:
        return Position.AGAINST if self is Position.FOR else Position.FOR


class ParticipantType(StrEnum):
    HUMAN = "human"
    SWARM = "swarm"


class Round(StrEnum):
    OPENING = "opening"
    REBUTTAL = "rebuttal"
    CROSS_EXAM = "cross_exam"
    CLOSING = "closing"


ROUND_ORDER: tuple[Round, ...] = (Round.OPENING, Round.REBUTTAL, Round.CROSS_EXAM, Round.CLOSING)


class Status(StrEnum):
    WAITING_FOR_OPPONENT = "waiting_for_opponent"
    SWARM_FALLBACK_OFFERED = "swarm_fallback_offered"
    LOBBY = "lobby"  # video only: waiting for both debaters to be ready
    OPENING = "opening"
    REBUTTAL = "rebuttal"
    CROSS_EXAM = "cross_exam"
    CLOSING = "closing"
    JUDGING = "judging"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"

    @property
    def is_round(self) -> bool:
        return self in ROUND_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self in (Status.COMPLETED, Status.ABANDONED, Status.CANCELLED)

    @property
    def is_live(self) -> bool:
        return self.is_round or self in (Status.LOBBY, Status.JUDGING)


ROUND_STATUSES = {Status.OPENING, Status.REBUTTAL, Status.CROSS_EXAM, Status.CLOSING}


def status_for_round(r: Round) -> Status:
    return Status(r.value)


class TurnKind(StrEnum):
    ARGUMENT = "argument"
    QUESTION = "question"
    ANSWER = "answer"


class TurnSource(StrEnum):
    TYPED = "typed"
    TRANSCRIPT = "transcript"
    SWARM = "swarm"


class ModerationStatus(StrEnum):
    APPROVED = "approved"
    FLAGGED = "flagged"  # hidden pending review
    HIDDEN = "hidden"  # removed by an admin
    UNCHECKED = "unchecked"


class ClaimStatus(StrEnum):
    UNADDRESSED = "unaddressed"
    REBUTTED = "rebutted"
    CONCEDED = "conceded"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    MISATTRIBUTED = "misattributed"


class Persona(StrEnum):
    DATA_DRIVEN = "data_driven"
    MORAL_FRAMING = "moral_framing"
    ECONOMIC = "economic"
    CONTRARIAN = "contrarian"


class ModelTier(StrEnum):
    STANDARD = "standard"
    FLAGSHIP = "flagship"
    UTILITY = "utility"
    JUDGE = "judge"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"  # can watch/vote, cannot debate (e.g. injection strikes)
    BANNED = "banned"
    DELETED = "deleted"


def values(enum_cls: type[StrEnum]) -> str:
    """SQL literal list for CHECK constraints."""
    return ", ".join(f"'{m.value}'" for m in enum_cls)
