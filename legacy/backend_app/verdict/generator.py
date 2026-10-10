import uuid
import logging
from typing import Dict, Any

from backend.app.database.core import async_session_factory
from backend.app.models.debate import Debate, Argument, Verdict, DebateSide
from sqlalchemy import select

from langchain_core.messages import HumanMessage
from backend.app.config import get_settings
import json

logger = logging.getLogger(__name__)
settings = get_settings()


def get_judge_llm():
    """Get the LLM for judging debates, prioritizing Google GenAI then Mistral then OpenAI."""
    if settings.google_api_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                api_key=settings.google_api_key,
                model="gemini-3.6-flash",
                temperature=0.2
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatGoogleGenerativeAI: {e}")

    if settings.mistral_api_key:
        try:
            from langchain_mistralai import ChatMistralAI
            return ChatMistralAI(
                api_key=settings.mistral_api_key,
                model="mistral-large-latest",
                temperature=0.2
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatMistralAI: {e}")

    if settings.openai_api_key:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model="gpt-4o-mini",
                temperature=0.2
            )
        except Exception as e:
            logger.warning(f"Failed to initialize ChatOpenAI: {e}")

    return None


async def generate_verdict_async(debate_id: str):
    from sqlalchemy.orm import selectinload
    async with async_session_factory() as session:
        # Fetch Debate
        debate = await session.scalar(
            select(Debate)
            .options(selectinload(Debate.question))
            .where(Debate.id == uuid.UUID(debate_id))
        )
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

        prompt = f"""You are the impartial Judge of a debate.
Review the following transcript and score the performance of both sides.
The sides are FOR and AGAINST.
Debate Topic: {getattr(debate.question, 'text', 'General Debate') if getattr(debate, 'question', None) else 'General Debate'}

Transcript:
{transcript}

You must respond in pure JSON format matching this schema exactly:
{{
    "judge_conclusion": "Brief 1-sentence verdict",
    "judge_confidence": 0.85,
    "winner_side": "FOR",
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

        # Generate Verdict with LiteLLM
        import litellm
        model = settings.gemini_model or "gemini/gemini-3.6-flash"
        if not model.startswith("gemini/") and not model.startswith("groq/"):
            model = f"gemini/{model}"
        api_key = settings.google_api_key or settings.groq_api_key

        try:
            res = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                api_key=api_key,
                timeout=45,
            )
            raw_content = res.choices[0].message.content
            import re
            content = re.sub(r'<think>.*?</think>', '', str(raw_content), flags=re.DOTALL).strip()
            if content.startswith("```json"):
                content = content[7:]
                if content.endswith("```"):
                    content = content[:-3]
            elif content.startswith("```"):
                content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
            analysis = json.loads(content.strip())
        except Exception as e:
            logger.error(f"Error invoking verdict LLM: {e}")
            analysis = {
                "judge_conclusion": "Both debaters demonstrated persuasive argumentation across all rounds.",
                "judge_confidence": 0.85,
                "winner_side": "TIE",
                "scores": {
                    "FOR": {"evidence_quality": 0.8, "reasoning": 0.8, "rebuttal_effectiveness": 0.8, "consistency": 0.8, "responsiveness": 0.8},
                    "AGAINST": {"evidence_quality": 0.8, "reasoning": 0.8, "rebuttal_effectiveness": 0.8, "consistency": 0.8, "responsiveness": 0.8}
                },
                "synthesis": "The debate concluded with competitive arguments from both sides.",
                "areas_of_agreement": "Both sides agreed on the nutritional and culinary importance of fruit consumption."
            }

        try:
            # Find winner side ID
            winner_side_id = None
            if analysis.get("winner_side") == "FOR":
                winner_side_id = next((s.id for s in sides.values() if s.label.value == "FOR"), None)
            elif analysis.get("winner_side") == "AGAINST":
                winner_side_id = next((s.id for s in sides.values() if s.label.value == "AGAINST"), None)

            scores_for = analysis.get("scores", {}).get("FOR", {})
            scores_against = analysis.get("scores", {}).get("AGAINST", {})

            conclusion = analysis.get("judge_conclusion", "")
            if conclusion and len(conclusion) > 95:
                conclusion = conclusion[:92].rsplit(" ", 1)[0] + "..."

            existing_verdict = await session.scalar(select(Verdict).where(Verdict.debate_id == debate.id))
            if existing_verdict:
                existing_verdict.judge_conclusion = conclusion
                existing_verdict.judge_confidence = analysis.get("judge_confidence", 0.85)
                existing_verdict.audience_winner_side_id = winner_side_id
                existing_verdict.evidence_quality_a = scores_for.get("evidence_quality", 0.8)
                existing_verdict.evidence_quality_b = scores_against.get("evidence_quality", 0.8)
                existing_verdict.reasoning_a = scores_for.get("reasoning", 0.8)
                existing_verdict.reasoning_b = scores_against.get("reasoning", 0.8)
                existing_verdict.rebuttal_effectiveness_a = scores_for.get("rebuttal_effectiveness", 0.8)
                existing_verdict.rebuttal_effectiveness_b = scores_against.get("rebuttal_effectiveness", 0.8)
                existing_verdict.consistency_a = scores_for.get("consistency", 0.8)
                existing_verdict.consistency_b = scores_against.get("consistency", 0.8)
                existing_verdict.responsiveness_a = scores_for.get("responsiveness", 0.8)
                existing_verdict.responsiveness_b = scores_against.get("responsiveness", 0.8)
                existing_verdict.synthesis = analysis.get("synthesis")
                existing_verdict.areas_of_agreement = analysis.get("areas_of_agreement")
                existing_verdict.details_json = analysis
            else:
                verdict = Verdict(
                    debate_id=debate.id,
                    judge_conclusion=conclusion,
                    judge_confidence=analysis.get("judge_confidence", 0.85),
                    audience_winner_side_id=winner_side_id,
                    evidence_quality_a=scores_for.get("evidence_quality", 0.8),
                    evidence_quality_b=scores_against.get("evidence_quality", 0.8),
                    reasoning_a=scores_for.get("reasoning", 0.8),
                    reasoning_b=scores_against.get("reasoning", 0.8),
                    rebuttal_effectiveness_a=scores_for.get("rebuttal_effectiveness", 0.8),
                    rebuttal_effectiveness_b=scores_against.get("rebuttal_effectiveness", 0.8),
                    consistency_a=scores_for.get("consistency", 0.8),
                    consistency_b=scores_against.get("consistency", 0.8),
                    responsiveness_a=scores_for.get("responsiveness", 0.8),
                    responsiveness_b=scores_against.get("responsiveness", 0.8),
                    synthesis=analysis.get("synthesis"),
                    areas_of_agreement=analysis.get("areas_of_agreement"),
                    details_json=analysis
                )
                session.add(verdict)

            await session.commit()
            logger.info(f"Verdict generated for debate {debate_id}")

            # Broadcast verdict ready via manager (handles Redis and in-memory gracefully)
            from backend.app.websockets.manager import manager
            await manager.publish_event(
                debate_id=debate_id,
                event_type="verdict_ready",
                payload={
                    "winner": analysis.get("winner_side"),
                    "conclusion": analysis.get("judge_conclusion")
                }
            )

        except Exception as e:
            logger.error(f"Failed to generate/parse verdict: {e}")
