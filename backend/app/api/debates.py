"""PROVOK — Debates API routes."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Any, List
from sqlalchemy import select
from uuid import UUID

from backend.app.dependencies import DbSession, get_current_user
from backend.app.models.user import User
from backend.app.models.debate import (
    Debate, Participant, PositionHistory, SideLabel, DebateStatus,
    Argument, DebateType, DebateSide, Round
)
from backend.app.schemas.debate import DebateCreate, DebateResponse, ArgumentCreate, ArgumentResponse
from backend.app.debate.state_machine import DebateStateMachine

router = APIRouter()

from fastapi import BackgroundTasks

@router.post("/", response_model=DebateResponse)
async def create_debate(
    debate_in: DebateCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: User = Depends(get_current_user)
) -> Any:
    """Create a new debate."""
    # Determine DebateType from opponent_type
    dt = DebateType.HUMAN_VS_AI
    if debate_in.opponent_type.value == "HUMAN":
        dt = DebateType.HUMAN_VS_HUMAN
    elif debate_in.opponent_type.value == "AI_VS_AI":
        dt = DebateType.AI_VS_AI

    # Create the underlying question record
    from backend.app.models.debate import Question
    question = Question(
        text=debate_in.title,
        author_id=current_user.id
    )
    db.add(question)
    await db.flush()

    debate = Debate(
        question_id=question.id,
        debate_type=dt,
        mode=debate_in.mode,
        visibility="PUBLIC" if debate_in.is_public else "PRIVATE"
    )
    db.add(debate)
    await db.flush()

    # Create sides
    side_for = DebateSide(debate_id=debate.id, label=SideLabel.FOR, position="For")
    side_against = DebateSide(debate_id=debate.id, label=SideLabel.AGAINST, position="Against")
    db.add_all([side_for, side_against])
    await db.flush()

    user_side_id = side_for.id if debate_in.initial_position == SideLabel.FOR else side_against.id

    # Add creator as participant
    participant = Participant(
        debate_id=debate.id,
        user_id=current_user.id,
        side_id=user_side_id,
        participant_type="HUMAN",
        initial_position=debate_in.initial_position.value,
        initial_confidence=1.0
    )
    db.add(participant)
    await db.flush()

    # Add initial position history
    pos_history = PositionHistory(
        debate_id=debate.id,
        participant_id=participant.id,
        position=debate_in.initial_position.value,
        confidence=1.0,
        phase="BEFORE"
    )
    db.add(pos_history)
    
    # Initialize FSM and first round
    fsm = DebateStateMachine(db)
    debate = await fsm.initialize_debate(debate)
    
    # Trigger AI opponent to respond if applicable
    if dt in [DebateType.HUMAN_VS_AI, DebateType.AI_VS_AI]:
        from backend.app.workers.ai_tasks import _generate_response_async
        background_tasks.add_task(_generate_response_async, str(debate.id))

    # Return explicit response to avoid async lazy load errors
    from datetime import datetime, timezone
    return DebateResponse(
        id=debate.id,
        title=debate_in.title,
        mode=debate.mode,
        opponent_type=debate_in.opponent_type,
        topic_id=debate_in.topic_id,
        is_public=debate_in.is_public,
        status=debate.status,
        creator_id=current_user.id,
        created_at=debate.created_at or datetime.now(timezone.utc),
        current_round=debate.current_round,
        rounds=[]
    )

@router.get("/{debate_id}", response_model=DebateResponse)
async def get_debate(debate_id: UUID, db: DbSession) -> Any:
    """Get debate details."""
    from sqlalchemy.orm import selectinload
    debate = await db.scalar(
        select(Debate)
        .options(
            selectinload(Debate.question),
            selectinload(Debate.participants),
            selectinload(Debate.rounds).selectinload(Round.arguments),
        )
        .where(Debate.id == debate_id)
    )
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    from datetime import datetime, timezone
    # Build explicit response to avoid lazy-load issues with @property fields
    rounds_data = []
    for r in debate.rounds:
        args_data = []
        for a in r.arguments:
            args_data.append({
                "id": a.id,
                "debate_id": a.debate_id,
                "participant_id": a.participant_id,
                "round_id": a.round_id,
                "side_id": a.side_id,
                "content": a.content,
                "argument_type": a.argument_type.value if hasattr(a.argument_type, 'value') else a.argument_type,
                "created_at": a.created_at,
                "claims": [],
            })
        rounds_data.append({
            "id": r.id,
            "debate_id": r.debate_id,
            "round_number": r.round_number,
            "phase": r.phase,
            "started_at": r.started_at,
            "ended_at": r.completed_at,
            "arguments": args_data,
        })

    creator_id = None
    for p in debate.participants:
        if str(p.participant_type) in ("HUMAN", "ParticipantType.HUMAN"):
            creator_id = p.user_id
            break

    from backend.app.schemas.debate import DebateResponse, ParticipantType as PT, DebateMode
    return DebateResponse(
        id=debate.id,
        title=debate.question.text if debate.question else "Debate",
        mode=debate.mode,
        opponent_type=PT.AI_SWARM,
        topic_id=None,
        is_public=(str(debate.visibility) in ("PUBLIC", "DebateVisibility.PUBLIC")),
        status=debate.status,
        creator_id=creator_id or debate.id,
        created_at=debate.created_at or datetime.now(timezone.utc),
        current_round=debate.current_round,
        rounds=rounds_data,
    )

from fastapi import BackgroundTasks

@router.post("/{debate_id}/turn", response_model=ArgumentResponse)
async def submit_turn(
    debate_id: UUID,
    arg_in: ArgumentCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: User = Depends(get_current_user)
) -> Any:
    """Submit an argument for the current turn."""
    debate = await db.scalar(select(Debate).where(Debate.id == debate_id))
    if not debate or debate.status != DebateStatus.LIVE:
        raise HTTPException(status_code=400, detail="Debate is not active")

    # Get participant side
    participant = await db.scalar(
        select(Participant).where(
            Participant.debate_id == debate_id, 
            Participant.user_id == current_user.id
        )
    )
    if not participant:
        raise HTTPException(status_code=403, detail="Not a participant in this debate")

    # Get current round
    from backend.app.models.debate import Round
    current_round_obj = await db.scalar(
        select(Round).where(Round.debate_id == debate_id, Round.round_number == debate.current_round)
    )
    if not current_round_obj:
        raise HTTPException(status_code=400, detail="No active round found")

    argument = Argument(
        debate_id=debate_id,
        round_id=current_round_obj.id,
        participant_id=participant.id,
        side_id=participant.side_id,
        content=arg_in.content,
        argument_type=arg_in.argument_type,
        sequence=1, # simplified
    )
    db.add(argument)
    await db.commit()
    await db.refresh(argument)
    
    # Broadcast argument to websockets via Redis PubSub
    from backend.app.websockets.manager import manager
    if hasattr(argument, '__dict__'):
        arg_data = {
            "id": str(argument.id),
            "content": argument.content,
            "side": participant.side_id.hex,
            "is_ai": False,
            "type": argument.argument_type.value,
        }
        import asyncio
        asyncio.create_task(manager.publish_event(
            debate_id=str(debate_id),
            event_type="argument_submitted",
            payload=arg_data
        ))
    
    # Check if we should trigger AI response
    if debate.debate_type in [DebateType.HUMAN_VS_AI, DebateType.AI_VS_AI]:
        from backend.app.workers.ai_tasks import _generate_response_async
        # Use FastAPI BackgroundTasks instead of Celery so it runs locally without Redis
        background_tasks.add_task(_generate_response_async, str(debate.id))

    from datetime import datetime, timezone
    return {
        "id": argument.id,
        "debate_id": argument.debate_id,
        "participant_id": argument.participant_id,
        "round_id": argument.round_id,
        "side_id": argument.side_id,
        "content": argument.content,
        "argument_type": argument.argument_type.value if hasattr(argument.argument_type, 'value') else argument.argument_type,
        "created_at": argument.created_at or datetime.now(timezone.utc),
        "claims": [],
    }

@router.post("/{debate_id}/done")
async def finish_turn(debate_id: UUID, db: DbSession, current_user: User = Depends(get_current_user)):
    """Explicitly finish turn and advance state machine if appropriate."""
    fsm = DebateStateMachine(db)
    await fsm.register_turn_completion(debate_id, current_user.id)
    return {"message": "Turn finished"}

@router.post("/{debate_id}/vote")
async def vote_on_argument(
    debate_id: UUID, 
    argument_id: UUID, 
    db: DbSession, 
    current_user: User = Depends(get_current_user)
):
    """Audience members cast a vote for a specific argument."""
    from backend.app.models.debate import Vote
    
    debate = await db.scalar(select(Debate).where(Debate.id == debate_id))
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    existing_vote = await db.scalar(
        select(Vote).where(Vote.user_id == current_user.id, Vote.argument_id == argument_id)
    )
    if existing_vote:
        raise HTTPException(status_code=400, detail="Already voted on this argument")
        
    vote = Vote(
        debate_id=debate_id,
        argument_id=argument_id,
        user_id=current_user.id
    )
    db.add(vote)
    await db.commit()
    
    # Broadcast vote count update
    from backend.app.websockets.manager import manager
    import asyncio
    asyncio.create_task(manager.publish_event(
        debate_id=str(debate_id),
        event_type="vote_registered",
        payload={"argument_id": str(argument_id)}
    ))
    return {"status": "success"}

from pydantic import BaseModel
class ChallengeCreate(BaseModel):
    content: str

@router.post("/{debate_id}/challenge")
async def submit_challenge(
    debate_id: UUID,
    challenge_in: ChallengeCreate,
    db: DbSession,
    current_user: User = Depends(get_current_user)
):
    """Audience submits a real-time challenge or question."""
    from backend.app.models.debate import AudienceChallenge
    debate = await db.scalar(select(Debate).where(Debate.id == debate_id))
    if not debate or debate.status != DebateStatus.LIVE:
        raise HTTPException(status_code=400, detail="Debate not active")

    # Get the actual Round object for this debate's current round
    from backend.app.models.debate import Round as RoundModel
    current_round_obj = await db.scalar(
        select(RoundModel).where(
            RoundModel.debate_id == debate_id,
            RoundModel.round_number == debate.current_round
        )
    )
    if not current_round_obj:
        raise HTTPException(status_code=400, detail="No active round found")

    challenge = AudienceChallenge(
        debate_id=debate_id,
        round_id=current_round_obj.id,
        user_id=current_user.id,
        content=challenge_in.content
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    
    from backend.app.websockets.manager import manager
    import asyncio
    asyncio.create_task(manager.publish_event(
        debate_id=str(debate_id),
        event_type="new_challenge",
        payload={"id": str(challenge.id), "content": challenge.content, "user": current_user.username}
    ))
    
    return {"status": "success", "challenge_id": challenge.id}

@router.get("/{debate_id}/verdict")
async def get_debate_verdict(debate_id: UUID, db: DbSession):
    """Retrieve the AI verdict and scorecard for a completed debate."""
    from backend.app.models.debate import Verdict
    verdict = await db.scalar(select(Verdict).where(Verdict.debate_id == debate_id))
    if not verdict:
        raise HTTPException(status_code=404, detail="Verdict not found or debate still ongoing")
    return verdict

