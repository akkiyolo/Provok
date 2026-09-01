import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
import uuid

from backend.app.models.debate import (
    Debate,
    DebateStatus,
    Round,
    RoundPhase,
    Turn,
    TurnStatus
)

logger = logging.getLogger(__name__)

class DebateStateMachine:
    """
    Finite State Machine for PROVOK Debates.
    Enforces strict 4-round progression:
    1. OPENING
    2. REBUTTAL
    3. EVIDENCE_CHALLENGE
    4. CLOSING
    """
    
    PHASE_PROGRESSION = [
        RoundPhase.OPENING,
        RoundPhase.REBUTTAL,
        RoundPhase.CROSS_EXAMINATION,
        RoundPhase.CLOSING
    ]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def initialize_debate(self, debate: Debate) -> Debate:
        """Starts a debate and creates the first round."""
        if debate.status != DebateStatus.DRAFT:
            raise ValueError(f"Cannot initialize debate in status {debate.status}")
        
        # Create first round
        first_round = Round(
            debate_id=debate.id,
            round_number=1,
            phase=RoundPhase.OPENING,
            started_at=datetime.now(timezone.utc)
        )
        self.db.add(first_round)
        await self.db.flush()

        # Update debate status
        debate.status = DebateStatus.LIVE
        debate.current_round = first_round.round_number
        
        await self.db.commit()
        await self.db.refresh(debate)
        return debate

    async def advance_round(self, debate: Debate) -> Optional[Round]:
        """Advances the debate to the next round, or completes it if 4 rounds are done."""
        if debate.status != DebateStatus.LIVE:
            raise ValueError("Can only advance active debates.")
            
        current_round = await self.db.scalar(
            select(Round).where(
                Round.debate_id == debate.id,
                Round.round_number == debate.current_round
            )
        )
        if not current_round:
            raise ValueError("No active round found for debate.")

        # Complete current round
        current_round.ended_at = datetime.now(timezone.utc)
        
        # Determine next phase
        current_idx = self.PHASE_PROGRESSION.index(current_round.phase)
        
        if current_idx + 1 >= len(self.PHASE_PROGRESSION):
            # Debate is finished
            debate.status = DebateStatus.COMPLETED
            debate.current_round = 0
            debate.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            # Trigger Verdict Generation
            from backend.app.workers.verdict_tasks import generate_verdict
            generate_verdict.delay(str(debate.id))
            
            return None
            
        # Create next round
        next_phase = self.PHASE_PROGRESSION[current_idx + 1]
        next_round = Round(
            debate_id=debate.id,
            round_number=current_round.round_number + 1,
            phase=next_phase,
            started_at=datetime.now(timezone.utc)
        )
        self.db.add(next_round)
        await self.db.flush()
        
        debate.current_round = next_round.round_number
        await self.db.commit()
        await self.db.refresh(next_round)
        
        return next_round

    async def register_turn_completion(self, debate_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Marks a turn as completed. If all participants have completed their turns 
        for the current round, advance the round.
        Returns True if the round was advanced.
        """
        debate = await self.db.scalar(select(Debate).where(Debate.id == debate_id))
        if not debate or debate.status != DebateStatus.LIVE:
            return False

        # In a real implementation, we would check all participants for this round.
        # For Phase 3, we simplify: when the AI replies, the round advances, 
        # or when both have submitted arguments.
        # This will be orchestrated by Celery tasks for AI and API for humans.
        
        # Example naive implementation: Just advance
        # await self.advance_round(debate)
        return False
