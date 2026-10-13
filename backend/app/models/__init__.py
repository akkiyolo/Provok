"""All ORM models, imported here so Alembic autogenerate sees the full metadata."""
from backend.app.models.debate import (
    Claim,
    Debate,
    DebateRound,
    ResearchCache,
    Side,
    Turn,
    Verdict,
    Vote,
)
from backend.app.models.platform import (
    AnalyticsEvent,
    AuditLog,
    Clip,
    CreditLedger,
    FeatureFlag,
    Follow,
    LLMCall,
    ModelRegistry,
    Notification,
    Payment,
    Report,
    VideoSession,
)
from backend.app.models.social import (
    Bookmark,
    Conversation,
    DailyDebate,
    DirectMessage,
    PollVote,
    Post,
    PostFactCheck,
    PostHashtag,
    PostLike,
    PostMedia,
    PostPoll,
    PostTranslation,
    UserBlock,
    UserMute,
)
from backend.app.models.user import AuthSession, EmailToken, OAuthAccount, User

__all__ = [
    "AnalyticsEvent", "AuditLog", "AuthSession", "Bookmark", "Claim", "Clip", "Conversation", "CreditLedger",
    "DailyDebate", "Debate", "DebateRound", "DirectMessage", "EmailToken", "FeatureFlag", "Follow", "LLMCall",
    "ModelRegistry", "Notification", "OAuthAccount", "Payment", "PollVote", "Post", "PostFactCheck", "PostHashtag",
    "PostLike", "PostMedia", "PostPoll", "PostTranslation", "Report", "ResearchCache", "Side", "Turn", "User",
    "UserBlock", "UserMute", "Verdict", "VideoSession", "Vote",
]
