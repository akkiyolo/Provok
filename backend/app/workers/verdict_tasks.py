"""PROVOK — Verdict background tasks."""
from backend.app.workers.celery_app import celery_app


import asyncio
import uuid
import logging
from typing import Dict, Any

from backend.app.database.core import async_session_factory
from backend.app.models.debate import Debate, Argument, Verdict, DebateSide
from sqlalchemy import select

from langchain_mistralai import ChatMistralAI
from langchain_core.messages import HumanMessage
from backend.app.config import get_settings
import json

logger = logging.getLogger(__name__)
settings = get_settings()

async def _generate_verdict_async(debate_id: str):
    async with async_session_factory() as session:
        # Fetch Debate
        debate = await session.scalar(select(Debate).where(Debate.id == uuid.UUID(debate_id)))
        if not debate:
            logger.error(f"Debate {debate_id} not found")
            return

        # Fetch Transcript
        arguments = await session.scalars(
            select(Argument).where(Argument.debate_id == debate.id).order_by(Argument.sequence)
        )
        transcript = ""
        sides = {} # maps side_id to label/position
        
        # Load Sides
        db_sides = await session.scalars(select(DebateSide).where(DebateSide.debate_id == debate.id))
        for side in db_sides:
            sides[side.id] = side

        # Build Transcript
        for arg in arguments:
            side_label = sides.get(arg.side_id).label if arg.side_id in sides else "UNKNOWN"
            transcript += f"[{side_label}] {arg.argument_type.value}: {arg.content}\n\n"

        # Initialize LLM
        llm = ChatMistralAI(
            api_key=settings.mistral_api_key,
            model="mistral-large-latest",
            temperature=0.2
        )

        prompt = f"""You are the impartial Judge of a debate.
Review the following transcript and score the performance of both sides.
The sides are FOR and AGAINST.
Debate Topic: {getattr(debate.question, 'text', 'General Debate') if hasattr(debate, 'question') else 'General Debate'}

Transcript:
{transcript}

You must respond in pure JSON format matching this schema exactly:
{{
    "judge_conclusion": "Brief 1-sentence verdict",
    "judge_confidence": 0.85,
    "winner_side": "FOR" or "AGAINST" or "TIE",
    "scores": {{
        "FOR": {{
            "evidence_quality": 0.9,
            "reasoning": 0.8,
            "rebuttal_effectiveness": 0.7,
            "consistency": 0.8,
            "responsiveness": 0.9
        }},
        "AGAINST": {{
            "evidence_quality": 0.6,
            "reasoning": 0.7,
            "rebuttal_effectiveness": 0.5,
            "consistency": 0.6,
            "responsiveness": 0.7
        }}
    }},
    "synthesis": "A 2-paragraph analysis of why this verdict was reached.",
    "areas_of_agreement": "List common ground discovered during the debate."
}}
"""
        
        response = llm.invoke([HumanMessage(content=prompt)])
        
        try:
            # Parse json
            content = response.content
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
                
            analysis = json.loads(content)
            
            # Find winner side ID
            winner_side_id = None
            if analysis.get("winner_side") == "FOR":
                winner_side_id = next((s.id for s in sides.values() if s.label.value == "FOR"), None)
            elif analysis.get("winner_side") == "AGAINST":
                winner_side_id = next((s.id for s in sides.values() if s.label.value == "AGAINST"), None)
                
            verdict = Verdict(
                debate_id=debate.id,
                judge_conclusion=analysis.get("judge_conclusion"),
                judge_confidence=analysis.get("judge_confidence"),
                audience_winner_side_id=winner_side_id, # Simplified, using AI judge as audience winner here for demo
                evidence_quality_a=analysis["scores"]["FOR"]["evidence_quality"],
                evidence_quality_b=analysis["scores"]["AGAINST"]["evidence_quality"],
                reasoning_a=analysis["scores"]["FOR"]["reasoning"],
                reasoning_b=analysis["scores"]["AGAINST"]["reasoning"],
                rebuttal_effectiveness_a=analysis["scores"]["FOR"]["rebuttal_effectiveness"],
                rebuttal_effectiveness_b=analysis["scores"]["AGAINST"]["rebuttal_effectiveness"],
                consistency_a=analysis["scores"]["FOR"]["consistency"],
                consistency_b=analysis["scores"]["AGAINST"]["consistency"],
                responsiveness_a=analysis["scores"]["FOR"]["responsiveness"],
                responsiveness_b=analysis["scores"]["AGAINST"]["responsiveness"],
                synthesis=analysis.get("synthesis"),
                areas_of_agreement=analysis.get("areas_of_agreement"),
                details_json=analysis
            )
            
            session.add(verdict)
            await session.commit()
            logger.info(f"Verdict generated for debate {debate_id}")
            
            # Broadcast verdict ready
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(settings.redis_url)
            event = {
                "debate_id": debate_id,
                "event_type": "verdict_ready",
                "payload": {"winner": analysis.get("winner_side"), "conclusion": analysis.get("judge_conclusion")}
            }
            await redis_client.publish("debate_events", json.dumps(event))
            await redis_client.close()
            
        except Exception as e:
            logger.error(f"Failed to generate/parse verdict: {e}")

@celery_app.task(name="verdict.generate", bind=True, max_retries=2)
def generate_verdict(self, debate_id: str):
    """Generate verdict after debate completion. Phase 7."""
    asyncio.run(_generate_verdict_async(debate_id))
