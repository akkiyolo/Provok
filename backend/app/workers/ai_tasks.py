"""PROVOK — AI background tasks."""
from backend.app.workers.celery_app import celery_app


import asyncio
import uuid
import logging
from typing import List

from backend.app.workers.celery_app import celery_app
from backend.app.database.core import async_session_factory
from backend.app.models.debate import Debate, Argument, Participant
from sqlalchemy import select

from backend.app.ai.swarm import create_swarm_graph, DebateState
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)

async def _generate_response_async(debate_id: str):
    async with async_session_factory() as session:
        debate = await session.scalar(select(Debate).where(Debate.id == uuid.UUID(debate_id)))
        if not debate:
            logger.error(f"Debate {debate_id} not found")
            return

        # Fetch recent arguments
        arguments = await session.scalars(
            select(Argument).where(Argument.debate_id == debate.id).order_by(Argument.sequence)
        )
        
        # Get current round
        from backend.app.models.debate import Round
        current_round_obj = await session.scalar(
            select(Round).where(Round.debate_id == debate.id, Round.round_number == debate.current_round)
        )

        # Build message history for LangGraph
        messages = []
        for arg in arguments:
            # Check participant type to determine if AI
            p = await session.scalar(select(Participant).where(Participant.id == arg.participant_id))
            if p and p.participant_type == "AI_SWARM":
                messages.append(AIMessage(content=arg.content))
            else:
                messages.append(HumanMessage(content=arg.content))

        # Get AI participant side
        ai_participant = await session.scalar(
            select(Participant).where(Participant.debate_id == debate.id, Participant.participant_type == "AI_SWARM")
        )
        if not ai_participant:
            logger.error("No AI participant found")
            return

        # Initialize Swarm
        app = create_swarm_graph()
        initial_state: DebateState = {
            "messages": messages,
            "next_node": "",
            "context": debate.question.text if getattr(debate, 'question', None) else "General Debate",
            "round_phase": "OPENING",
            "draft_argument": "",
            "research_points": ""
        }

        # Run swarm
        final_state = app.invoke(initial_state)
        final_message = final_state["messages"][-1].content

        # Save AI response
        new_arg = Argument(
            debate_id=debate.id,
            round_id=current_round_obj.id if current_round_obj else None,
            participant_id=ai_participant.id,
            side_id=ai_participant.side_id,
            content=final_message,
            argument_type="OPENING", # Determine properly
            sequence=len(messages) + 1
        )
        session.add(new_arg)
        await session.commit()
        await session.refresh(new_arg)
        logger.info(f"AI response generated for debate {debate_id}")

        # Broadcast via WebSocket manager
        from backend.app.websockets.manager import manager
        payload = {
            "id": str(new_arg.id),
            "content": new_arg.content,
            "side": ai_participant.side_id.hex,
            "is_ai": True,
            "type": new_arg.argument_type.value if hasattr(new_arg.argument_type, 'value') else new_arg.argument_type,
        }
        await manager.publish_event(
            debate_id=debate_id,
            event_type="argument_submitted",
            payload=payload
        )

@celery_app.task(name="ai.generate_response", bind=True, max_retries=3)
def generate_ai_response(self, debate_id: str):
    """Run AI swarm graph to generate a debate response."""
    asyncio.run(_generate_response_async(debate_id))


@celery_app.task(name="ai.stream_response", bind=True, max_retries=3)
def stream_ai_response(self, debate_id: str, round_id: str):
    """Stream AI response via WebSocket. Phase 5."""
    pass
