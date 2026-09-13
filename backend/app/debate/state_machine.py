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
    3. CROSS_EXAMINATION
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
        
        await self.db.flush()
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
        current_round.completed_at = datetime.now(timezone.utc)
        
        # Determine next phase
        current_idx = self.PHASE_PROGRESSION.index(current_round.phase)
        
        if current_idx + 1 >= len(self.PHASE_PROGRESSION):
            # Debate is finished after 4 rounds
            debate.status = DebateStatus.COMPLETED
            debate.completed_at = datetime.now(timezone.utc)
            await self.db.flush()
            
            # Trigger Verdict Generation
            try:
                import asyncio
                from backend.app.verdict.generator import generate_verdict_async
                asyncio.create_task(generate_verdict_async(str(debate.id)))
                logger.info(f"Verdict generation task triggered for debate {debate.id}")
            except Exception as e:
                logger.warning(f"Could not launch verdict task: {e}")
            
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
        await self.db.flush()
        await self.db.refresh(next_round)
        
        return next_round

    async def get_current_round(self, debate: Debate) -> Optional[Round]:
        """Fetch the active round object for the debate."""
        return await self.db.scalar(
            select(Round).where(
                Round.debate_id == debate.id,
                Round.round_number == debate.current_round
            )
        )

    async def should_advance_round(self, debate: Debate) -> bool:
        """
        Check if both sides have submitted at least one argument for the current round.
        """
        current_round = await self.get_current_round(debate)
        if not current_round:
            return False

        from backend.app.models.debate import Argument
        from sqlalchemy import func
        args_count = await self.db.scalar(
            select(func.count()).select_from(Argument).where(
                Argument.debate_id == debate.id,
                Argument.round_id == current_round.id
            )
        )
        return (args_count or 0) >= 2
