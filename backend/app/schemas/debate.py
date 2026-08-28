from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from backend.app.models.debate import (
    DebateMode,
    DebateStatus,
    ParticipantType,
    SideLabel,
    RoundPhase,
)

# ── Arguments & Claims ─────────────────────────────────────
class ClaimBase(BaseModel):
    content: str
    is_contested: bool = False

class ClaimResponse(ClaimBase):
    id: UUID
    argument_id: UUID
    debate_id: UUID

    class Config:
        from_attributes = True

class ArgumentBase(BaseModel):
    content: str
    argument_type: str = "OPENING"

class ArgumentCreate(ArgumentBase):
    pass

class ArgumentResponse(ArgumentBase):
    id: UUID
    debate_id: UUID
    user_id: Optional[UUID]
    round_id: UUID
    is_ai: bool
    side: SideLabel
    created_at: datetime
    claims: List[ClaimResponse] = []

    class Config:
        from_attributes = True

# ── Rounds & Turns ─────────────────────────────────────────
class RoundResponse(BaseModel):
    id: UUID
    debate_id: UUID
    round_number: int
    phase: RoundPhase
    started_at: datetime
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ── Debate ─────────────────────────────────────────────────
class DebateBase(BaseModel):
    title: str = Field(..., max_length=200)
    mode: DebateMode = DebateMode.ASYNC
    opponent_type: ParticipantType = ParticipantType.AI_SWARM
    topic_id: Optional[UUID] = None
    is_public: bool = True

class DebateCreate(DebateBase):
    initial_position: SideLabel = SideLabel.FOR

class DebateResponse(DebateBase):
    id: UUID
    status: DebateStatus
    creator_id: UUID
    created_at: datetime
    current_round: int = 0
    rounds: List[RoundResponse] = []

    class Config:
        from_attributes = True
