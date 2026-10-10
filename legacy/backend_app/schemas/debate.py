from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from backend.app.models.debate import DebateStatus, DebateMode, SideLabel, RoundPhase, ParticipantType

# ── Claims ─────────────────────────────────────────────────
class ClaimBase(BaseModel):
    content: str
    is_contested: bool = False

class ClaimResponse(ClaimBase):
    id: UUID
    argument_id: UUID
    debate_id: UUID
    model_config = ConfigDict(from_attributes=True)

class ArgumentBase(BaseModel):
    content: str
    argument_type: str = "OPENING"

class ArgumentCreate(ArgumentBase):
    pass

class ArgumentResponse(ArgumentBase):
    id: UUID
    debate_id: UUID
    participant_id: UUID
    round_id: UUID
    side_id: UUID
    side: Optional[str] = None
    is_ai: Optional[bool] = False
    agent_name: Optional[str] = None
    badges: List[str] = []
    created_at: datetime
    claims: List[ClaimResponse] = []
    model_config = ConfigDict(from_attributes=True)

# ── Rounds & Turns ─────────────────────────────────────────
class RoundResponse(BaseModel):
    id: UUID
    debate_id: UUID
    round_number: int
    phase: RoundPhase
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    arguments: List[ArgumentResponse] = []
    model_config = ConfigDict(from_attributes=True)

# ── Debate ─────────────────────────────────────────────────
class DebateBase(BaseModel):
    title: str = Field(..., max_length=200)
    mode: DebateMode = DebateMode.ASYNC
    opponent_type: str = "AI_SWARM"
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
    model_config = ConfigDict(from_attributes=True)
