"""
PROVOK — ORM Models package.

All models are imported here so Alembic can discover them from Base.metadata.
"""

from backend.app.models.user import User, OAuthAccount
from backend.app.models.debate import (
    Question,
    Topic,
    QuestionTopic,
    Debate,
    DebateSide,
    Participant,
    Round,
    Turn,
    Message,
    Argument,
    Claim,
    Evidence,
    ArgumentEvidence,
    Vote,
    RoundVote,
    AudienceChallenge,
    Verdict,
    PositionHistory,
)
from backend.app.models.social import (
    Follow,
    Interaction,
    Notification,
    Recommendation,
)
from backend.app.models.files import File, FileChunk, Embedding
from backend.app.models.analytics import AuditEvent

__all__ = [
    "User", "OAuthAccount",
    "Question", "Topic", "QuestionTopic",
    "Debate", "DebateSide", "Participant",
    "Round", "Turn", "Message", "Argument",
    "Claim", "Evidence", "ArgumentEvidence",
    "Vote", "RoundVote", "AudienceChallenge",
    "Verdict", "PositionHistory",
    "Follow", "Interaction", "Notification", "Recommendation",
    "File", "FileChunk", "Embedding",
    "AuditEvent",
]
