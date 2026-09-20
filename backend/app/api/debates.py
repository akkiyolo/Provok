"""PROVOK — Debates API routes."""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response, Request
from typing import Any, List, Optional
from sqlalchemy import select
from uuid import UUID

from backend.app.dependencies import DbSession, get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.models.debate import (
    Debate, Participant, PositionHistory, SideLabel, DebateStatus,
    Argument, DebateType, DebateSide, Round, ParticipantType, Verdict
)
from backend.app.schemas.debate import DebateCreate, DebateResponse, ArgumentCreate, ArgumentResponse
from backend.app.debate.state_machine import DebateStateMachine
from backend.app.config import get_settings
from backend.app.limiter import limiter

def _get_dialectical_badges(round_number: int, argument_type: Any, side: str) -> list[str]:
    arg_type_str = argument_type.value if hasattr(argument_type, 'value') else str(argument_type or "").upper()
    side_str = str(side).upper()
    if round_number == 1:
        return ["Core Thesis", "Empirical Baseline"] if side_str == "FOR" else ["Counter-Thesis", "Empirical Challenge"]
    elif round_number == 2:
        return ["Direct Refutation", "Premise Attack"] if side_str == "FOR" else ["Logical Scrutiny", "Fallacy Exposure"]
    elif round_number == 3:
        return ["Socratic Probe", "Direct Inquiry"] if "QUESTION" in arg_type_str else ["Cross-Defense", "Clarification"]
    elif round_number == 4:
        return ["Closing Synthesis", "Impact Calculus"] if side_str == "FOR" else ["Final Defense", "Ethical Grounding"]
    return ["Argument Point"]

settings = get_settings()
router = APIRouter()


@router.get("/", response_model=List[DebateResponse])
async def list_debates(db: DbSession, status: Optional[str] = None, limit: int = 10) -> Any:
    """Get a list of recent public debates."""
    from sqlalchemy.orm import selectinload
    
    query = select(Debate).options(
        selectinload(Debate.question),
        selectinload(Debate.participants)
    ).where(Debate.visibility == "PUBLIC")
    if status:
        query = query.where(Debate.status == status)
        
    debates = await db.scalars(query.order_by(Debate.created_at.desc()).limit(limit))
    
    res = []
    for d in debates:
        # Map DebateType to opponent_type string for frontend
        opp_type = "AI_SWARM"
        if d.debate_type == DebateType.HUMAN_VS_HUMAN:
            opp_type = "HUMAN"
        elif d.debate_type == DebateType.AI_VS_AI:
            opp_type = "AI_VS_AI"
            
        res.append(DebateResponse(
            id=d.id,
            title=d.question.text if d.question else "Unknown Topic",
            mode=d.mode,
            opponent_type=opp_type, 
            is_public=True,
            status=d.status,
            creator_id=d.creator_id or UUID(int=0), 
            created_at=d.created_at,
            current_round=d.current_round,
            rounds=[]
        ))
    return res

@router.post("", response_model=DebateResponse)
@router.post("/", response_model=DebateResponse)
@limiter.limit(settings.rate_limit_create_debate)
async def create_debate(
    request: Request,
    debate_in: DebateCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: User = Depends(get_current_user)
) -> Any:
    """Create a new debate."""
    # Determine DebateType from opponent_type
    opp = str(debate_in.opponent_type).upper()
    if opp in ["AI_VS_AI", "AGENT_VS_AGENT"]:
        dt = DebateType.AI_VS_AI
    elif opp in ["HUMAN", "PARTICIPANTTYPE.HUMAN"]:
        dt = DebateType.HUMAN_VS_HUMAN
    else:
        dt = DebateType.HUMAN_VS_AI

    import uuid
    
    # Create the underlying question record
    from backend.app.models.debate import Question
    import bleach
    clean_title = bleach.clean(debate_in.title.strip(), tags=[], strip=True)
    if not clean_title:
        raise HTTPException(status_code=400, detail="Debate title cannot be empty.")
    question_id = uuid.uuid4()
    question = Question(
        id=question_id,
        text=clean_title,
        author_id=current_user.id
    )
    db.add(question)

    debate_id = uuid.uuid4()
    debate = Debate(
        id=debate_id,
        question_id=question.id,
        debate_type=dt,
        mode=debate_in.mode,
        visibility="PUBLIC" if debate_in.is_public else "PRIVATE",
        status=DebateStatus.DRAFT
    )
    db.add(debate)

    # Create sides
    side_for_id = uuid.uuid4()
    side_against_id = uuid.uuid4()
    side_for = DebateSide(id=side_for_id, debate_id=debate.id, label=SideLabel.FOR, position="For")
    side_against = DebateSide(id=side_against_id, debate_id=debate.id, label=SideLabel.AGAINST, position="Against")
    db.add_all([side_for, side_against])

    if dt == DebateType.AI_VS_AI:
        # Agent vs Agent: Two autonomous AI participants
        agent_for = Participant(
            id=uuid.uuid4(),
            debate_id=debate.id,
            user_id=None,
            side_id=side_for.id,
            participant_type=ParticipantType.AI_SWARM,
            initial_position=SideLabel.FOR.value,
            initial_confidence=1.0
        )
        agent_against = Participant(
            id=uuid.uuid4(),
            debate_id=debate.id,
            user_id=None,
            side_id=side_against.id,
            participant_type=ParticipantType.AI_SWARM,
            initial_position=SideLabel.AGAINST.value,
            initial_confidence=1.0
        )
        db.add_all([agent_for, agent_against])
    else:
        # Human vs Human or Human vs AI
        user_side_id = side_for.id if debate_in.initial_position == SideLabel.FOR else side_against.id

        # Add creator as participant
        participant_id = uuid.uuid4()
        participant = Participant(
            id=participant_id,
            debate_id=debate.id,
            user_id=current_user.id,
            side_id=user_side_id,
            participant_type=ParticipantType.HUMAN,
            initial_position=debate_in.initial_position.value,
            initial_confidence=1.0
        )
        db.add(participant)

        # Add AI participant if applicable
        if dt == DebateType.HUMAN_VS_AI:
            ai_side_id = side_against.id if debate_in.initial_position == SideLabel.FOR else side_for.id
            ai_participant = Participant(
                id=uuid.uuid4(),
                debate_id=debate.id,
                user_id=None,
                side_id=ai_side_id,
                participant_type=ParticipantType.AI_SWARM,
                initial_position=SideLabel.AGAINST.value if debate_in.initial_position == SideLabel.FOR else SideLabel.FOR.value,
                initial_confidence=1.0
            )
            db.add(ai_participant)

        # Flush participants so participant.id is persisted before position_history references it
        await db.flush()

        # Add initial position history
        pos_history = PositionHistory(
            id=uuid.uuid4(),
            debate_id=debate.id,
            participant_id=participant.id,
            position=debate_in.initial_position.value,
            confidence=1.0,
            phase="BEFORE"
        )
        db.add(pos_history)
        await db.flush()
    
    # Initialize FSM and first round
    fsm = DebateStateMachine(db)
    debate = await fsm.initialize_debate(debate)

    # Commit all debate, side, participant, and round records to ensure they are fully visible
    await db.commit()
    
    # Start tasks asynchronously without holding the HTTP response
    if dt == DebateType.AI_VS_AI:
        from backend.app.workers.ai_tasks import dispatch_agent_debate
        dispatch_agent_debate(str(debate.id))
    elif dt == DebateType.HUMAN_VS_AI and debate_in.initial_position == SideLabel.AGAINST:
        # If user picked AGAINST, AI takes FOR and delivers opening statement
        from backend.app.workers.ai_tasks import dispatch_ai_swarm_turn
        dispatch_ai_swarm_turn(str(debate.id))

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
            selectinload(Debate.sides),
            selectinload(Debate.rounds).selectinload(Round.arguments),
        )
        .where(Debate.id == debate_id)
    )
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    from datetime import datetime, timezone
    
    # Build a lookup for side labels
    side_lookup = {str(s.id): s.label.value if hasattr(s.label, 'value') else str(s.label) for s in debate.sides}

    import re
    is_ai_debate = (debate.debate_type == DebateType.AI_VS_AI)
    part_map = {p.id: p for p in debate.participants}

    rounds_data = []
    for r in debate.rounds:
        args_data = []
        for a in r.arguments:
            p = part_map.get(a.participant_id)
            side_val = side_lookup.get(str(a.side_id), "")
            is_ai = is_ai_debate or (p and p.participant_type in (ParticipantType.AI_SWARM, ParticipantType.AI_AGENT))
            agent_name = f"Agent {side_val}" if is_ai else (p.user.username if (p and p.user) else "Participant")
            
            clean_content = a.content or ""
            if "</think>" in clean_content:
                clean_content = clean_content.split("</think>")[-1].strip()
            else:
                clean_content = re.sub(r'<think>.*?</think>', '', clean_content, flags=re.DOTALL).strip()
                if clean_content.startswith("<think>"):
                    clean_content = clean_content.replace("<think>", "").strip()

            args_data.append({
                "id": a.id,
                "debate_id": a.debate_id,
                "participant_id": a.participant_id,
                "round_id": a.round_id,
                "side_id": a.side_id,
                "side": side_val,
                "is_ai": is_ai,
                "agent_name": agent_name,
                "content": clean_content,
                "argument_type": a.argument_type.value if hasattr(a.argument_type, 'value') else a.argument_type,
                "created_at": a.created_at,
                "claims": [],
                "badges": _get_dialectical_badges(r.round_number, a.argument_type, side_val),
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
        if p.participant_type == ParticipantType.HUMAN:
            creator_id = p.user_id
            break

    opp_type = "AI_SWARM"
    if debate.debate_type == DebateType.HUMAN_VS_HUMAN:
        opp_type = "HUMAN"
    elif debate.debate_type == DebateType.AI_VS_AI:
        opp_type = "AI_VS_AI"

    return DebateResponse(
        id=debate.id,
        title=debate.question.text if debate.question else "Debate",
        mode=debate.mode,
        opponent_type=opp_type,
        topic_id=None,
        is_public=(str(debate.visibility) in ("PUBLIC", "DebateVisibility.PUBLIC")),
        status=debate.status,
        creator_id=creator_id or debate.id,
        created_at=debate.created_at or datetime.now(timezone.utc),
        current_round=debate.current_round,
        rounds=rounds_data,
    )


@router.delete("/{debate_id}", status_code=204)
async def delete_debate(debate_id: UUID, db: DbSession, current_user: User = Depends(get_current_user)):
    """Delete a debate. Only the creator or an admin can delete it."""
    from sqlalchemy.orm import selectinload
    debate = await db.scalar(
        select(Debate)
        .options(selectinload(Debate.participants))
        .where(Debate.id == debate_id)
    )
    if not debate:
        raise HTTPException(status_code=404, detail="Debate not found")

    # Check ownership
    creator_id = None
    for p in debate.participants:
        if p.participant_type == ParticipantType.HUMAN:
            creator_id = p.user_id
            break
            
    if creator_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this debate")

    await db.delete(debate)
    return Response(status_code=204)

@router.post("/{debate_id}/turn", response_model=ArgumentResponse)
@limiter.limit(settings.rate_limit_argument)
async def submit_turn(
    request: Request,
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

    if debate.debate_type == DebateType.AI_VS_AI:
        raise HTTPException(
            status_code=400,
            detail="This is an autonomous Agent-vs-Agent debate. Spectators cannot submit arguments."
        )

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
    current_round_obj = await db.scalar(
        select(Round).where(Round.debate_id == debate_id, Round.round_number == debate.current_round)
    )
    if not current_round_obj:
        raise HTTPException(status_code=400, detail="No active round found")

    import bleach
    clean_content = bleach.clean(
        arg_in.content.strip(),
        tags=['p', 'b', 'i', 'strong', 'em', 'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'br', 'a'],
        attributes={'a': ['href', 'title', 'rel']},
        strip=True
    )
    if not clean_content:
        raise HTTPException(status_code=400, detail="Argument content cannot be empty.")

    phase_str = current_round_obj.phase.value if hasattr(current_round_obj.phase, 'value') else str(current_round_obj.phase)
    arg_type_map = {
        "OPENING": "OPENING",
        "REBUTTAL": "REBUTTAL",
        "CROSS_EXAMINATION": "QUESTION",
        "CLOSING": "CLOSING",
    }
    actual_arg_type = arg_type_map.get(phase_str, arg_in.argument_type)

    argument = Argument(
        debate_id=debate_id,
        round_id=current_round_obj.id,
        participant_id=participant.id,
        side_id=participant.side_id,
        content=clean_content,
        argument_type=actual_arg_type,
        sequence=1, # simplified
    )
    db.add(argument)
    await db.flush()
    await db.refresh(argument)
    
    # Broadcast argument to websockets via Redis PubSub
    from backend.app.websockets.manager import manager
    badges = _get_dialectical_badges(debate.current_round, argument.argument_type, participant.initial_position.value if hasattr(participant.initial_position, 'value') else str(participant.initial_position))
    arg_data = {
        "id": str(argument.id),
        "content": argument.content,
        "side": participant.initial_position.value if hasattr(participant.initial_position, 'value') else str(participant.initial_position),
        "is_ai": False,
        "type": argument.argument_type.value if hasattr(argument.argument_type, 'value') else argument.argument_type,
        "badges": badges,
    }
    await manager.publish_event(
        debate_id=str(debate_id),
        event_type="argument_submitted",
        payload=arg_data
    )
    
    # Check if we should trigger AI response (Celery worker or background fallback)
    if debate.debate_type in [DebateType.HUMAN_VS_AI, DebateType.AI_VS_AI]:
        from backend.app.workers.ai_tasks import dispatch_ai_swarm_turn
        dispatch_ai_swarm_turn(str(debate.id), background_tasks)

    # Get side label for response
    side_obj = await db.scalar(select(DebateSide).where(DebateSide.id == participant.side_id))
    side_label_str = side_obj.label.value if side_obj and hasattr(side_obj.label, 'value') else (str(side_obj.label) if side_obj else "")

    from datetime import datetime, timezone
    return {
        "id": argument.id,
        "debate_id": argument.debate_id,
        "participant_id": argument.participant_id,
        "round_id": argument.round_id,
        "side_id": argument.side_id,
        "side": side_label_str,
        "content": argument.content,
        "argument_type": argument.argument_type.value if hasattr(argument.argument_type, 'value') else argument.argument_type,
        "created_at": argument.created_at or datetime.now(timezone.utc),
        "claims": [],
        "badges": badges,
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
    
    # Broadcast vote count update — await directly instead of fire-and-forget
    from backend.app.websockets.manager import manager
    await manager.publish_event(
        debate_id=str(debate_id),
        event_type="vote_registered",
        payload={"argument_id": str(argument_id)}
    )
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
    current_round_obj = await db.scalar(
        select(Round).where(
            Round.debate_id == debate_id,
            Round.round_number == debate.current_round
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
    await db.flush()
    await db.refresh(challenge)
    
    # Broadcast — await directly
    from backend.app.websockets.manager import manager
    await manager.publish_event(
        debate_id=str(debate_id),
        event_type="new_challenge",
        payload={"id": str(challenge.id), "content": challenge.content, "user": current_user.username}
    )
    
    return {"status": "success", "challenge_id": challenge.id}

@router.get("/{debate_id}/verdict")
async def get_debate_verdict(debate_id: UUID, db: DbSession):
    """Retrieve the AI verdict and scorecard for a completed debate."""
    from backend.app.models.debate import Verdict, Debate
    from sqlalchemy.orm import selectinload
    verdict = await db.scalar(select(Verdict).where(Verdict.debate_id == debate_id))
    if not verdict:
        raise HTTPException(status_code=404, detail="Verdict not found or debate still ongoing")

    debate = await db.scalar(
        select(Debate).options(selectinload(Debate.question)).where(Debate.id == debate_id)
    )
    title = debate.question.text if (debate and debate.question) else "Debate Verdict"

    return {
        "id": str(verdict.id),
        "debate_id": str(verdict.debate_id),
        "debate_title": title,
        "judge_conclusion": verdict.judge_conclusion,
        "judge_confidence": verdict.judge_confidence,
        "synthesis": verdict.synthesis,
        "areas_of_agreement": verdict.areas_of_agreement,
        "evidence_quality_a": verdict.evidence_quality_a,
        "evidence_quality_b": verdict.evidence_quality_b,
        "reasoning_a": verdict.reasoning_a,
        "reasoning_b": verdict.reasoning_b,
        "rebuttal_effectiveness_a": verdict.rebuttal_effectiveness_a,
        "rebuttal_effectiveness_b": verdict.rebuttal_effectiveness_b,
        "consistency_a": verdict.consistency_a,
        "consistency_b": verdict.consistency_b,
        "responsiveness_a": verdict.responsiveness_a,
        "responsiveness_b": verdict.responsiveness_b,
        "details_json": verdict.details_json,
    }


# ── Audience Winner Poll ───────────────────────────────────────

class PollVoteCreate(BaseModel):
    side: str  # "FOR" or "AGAINST"


async def _get_poll_tally(debate_id: UUID, db: Any, voter_key: str = None) -> dict:
    verdict = await db.scalar(select(Verdict).where(Verdict.debate_id == debate_id))
    details = (verdict.details_json or {}) if verdict else {}
    poll = details.get("audience_poll", {"for_votes": 0, "against_votes": 0, "voters": {}})

    for_votes = int(poll.get("for_votes", 0))
    against_votes = int(poll.get("against_votes", 0))
    total = for_votes + against_votes

    for_pct = round((for_votes / total * 100), 1) if total > 0 else 50.0
    against_pct = round((against_votes / total * 100), 1) if total > 0 else 50.0

    winner = "TIE"
    if for_votes > against_votes:
        winner = "FOR"
    elif against_votes > for_votes:
        winner = "AGAINST"

    voted_side = poll.get("voters", {}).get(voter_key) if voter_key else None

    return {
        "debate_id": str(debate_id),
        "votes_for": for_votes,
        "votes_against": against_votes,
        "for_votes": for_votes,
        "against_votes": against_votes,
        "total_votes": total,
        "pct_for": for_pct,
        "pct_against": against_pct,
        "for_percent": for_pct,
        "against_percent": against_pct,
        "winner_side": winner,
        "community_winner": winner,
        "user_voted": voted_side
    }


@router.get("/{debate_id}/poll")
async def get_debate_poll(
    debate_id: UUID,
    request: Request,
    db: DbSession,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get current audience community poll tally for who won the debate."""
    voter_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")
    return await _get_poll_tally(debate_id, db, voter_key)


@router.post("/{debate_id}/poll")
async def vote_in_debate_poll(
    debate_id: UUID,
    vote_in: PollVoteCreate,
    request: Request,
    db: DbSession,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Cast an audience community vote on who won the debate (FOR vs AGAINST). Works across all 3 modes."""
    from sqlalchemy.orm.attributes import flag_modified
    from backend.app.websockets.manager import manager

    side = vote_in.side.strip().upper()
    if side not in ["FOR", "AGAINST"]:
        raise HTTPException(status_code=400, detail="Side must be 'FOR' or 'AGAINST'")

    voter_key = str(current_user.id) if current_user else (request.client.host if request.client else "anon")

    verdict = await db.scalar(select(Verdict).where(Verdict.debate_id == debate_id))
    if not verdict:
        # Create verdict draft record for ongoing/live poll if judge hasn't run yet
        verdict = Verdict(
            debate_id=debate_id,
            judge_conclusion="Community Poll Active",
            details_json={"audience_poll": {"for_votes": 0, "against_votes": 0, "voters": {}}}
        )
        db.add(verdict)
        await db.flush()

    details = dict(verdict.details_json or {})
    poll = dict(details.get("audience_poll", {"for_votes": 0, "against_votes": 0, "voters": {}}))
    voters = dict(poll.get("voters", {}))

    prev_vote = voters.get(voter_key)
    if prev_vote:
        if prev_vote == side:
            return await _get_poll_tally(debate_id, db, voter_key)
        # Switching vote
        if prev_vote == "FOR":
            poll["for_votes"] = max(0, poll.get("for_votes", 1) - 1)
        else:
            poll["against_votes"] = max(0, poll.get("against_votes", 1) - 1)

    if side == "FOR":
        poll["for_votes"] = poll.get("for_votes", 0) + 1
    else:
        poll["against_votes"] = poll.get("against_votes", 0) + 1

    voters[voter_key] = side
    poll["voters"] = voters
    details["audience_poll"] = poll
    verdict.details_json = details

    flag_modified(verdict, "details_json")
    await db.commit()

    tally = await _get_poll_tally(debate_id, db, voter_key)

    # Broadcast real-time poll update to all connected spectators
    await manager.publish_event(
        debate_id=str(debate_id),
        event_type="poll_updated",
        payload=tally
    )
    return tally
