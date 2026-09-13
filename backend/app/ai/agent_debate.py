"""
PROVOK — Autonomous Agent vs Agent Debate Engine.

Orchestrates two autonomous AI agents debating each other across all 4 rounds:
- Agent FOR: Powered by Groq (via LiteLLM, using GROQ_API_KEY)
- Agent AGAINST: Powered by Gemini (via LiteLLM, using GOOGLE_API_KEY)

Strictly dedicated for DebateType.AI_VS_AI debates.
Streams arguments in real time over WebSockets with human-like viewing pacing.
"""
import asyncio
import logging
import uuid
from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import litellm
from backend.app.config import get_settings
from backend.app.database.core import async_session_factory
from backend.app.models.debate import (
    Debate, Argument, DebateSide, Participant, ParticipantType,
    SideLabel, Round, RoundPhase, DebateStatus
)
from backend.app.debate.state_machine import DebateStateMachine
from backend.app.websockets.manager import manager
from backend.app.verdict.generator import generate_verdict_async

logger = logging.getLogger(__name__)
settings = get_settings()

# Disable noisy LiteLLM logs
litellm.suppress_debug_info = True


async def _generate_agent_turn(
    model: str,
    api_key: str,
    system_prompt: str,
    conversation_history: List[Dict[str, str]],
    turn_instruction: str,
) -> str:
    """Invoke an agent using LiteLLM."""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": turn_instruction})

    max_tokens = 850 if "groq" in model else 1200
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
    }
    if api_key:
        kwargs["api_key"] = api_key

    try:
        response = await litellm.acompletion(**kwargs)
        content = response.choices[0].message.content
        if isinstance(content, list):
            content = "\n".join([c.get("text", "") for c in content if isinstance(c, dict) and "text" in c])
        content_str = str(content)
        if "</think>" in content_str:
            clean_text = content_str.split("</think>")[-1].strip()
        else:
            import re
            clean_text = re.sub(r'<think>.*?</think>', '', content_str, flags=re.DOTALL).strip()
            if clean_text.startswith("<think>"):
                clean_text = clean_text.replace("<think>", "").strip()
        return clean_text or content_str.strip()
    except Exception as e:
        logger.error(f"Error invoking agent with {model}: {e}")
        # Fallback to gemini if groq fails or has rate limit
        if "groq" in model and settings.google_api_key:
            logger.info("Falling back to Gemini for agent turn...")
            kwargs["model"] = "gemini/gemini-3.6-flash"
            kwargs["api_key"] = settings.google_api_key
            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content
            content_str = str(content)
            if "</think>" in content_str:
                clean_text = content_str.split("</think>")[-1].strip()
            else:
                import re
                clean_text = re.sub(r'<think>.*?</think>', '', content_str, flags=re.DOTALL).strip()
                if clean_text.startswith("<think>"):
                    clean_text = clean_text.replace("<think>", "").strip()
            return clean_text or content_str.strip()
        raise e


async def run_agent_vs_agent_debate(debate_id: str) -> None:
    """
    Main loop executing all 4 rounds of an autonomous Agent vs Agent debate.
    """
    raw_groq = settings.groq_model or "groq/qwen/qwen3.6-27b"
    groq_model = raw_groq if raw_groq.startswith("groq/") else f"groq/{raw_groq}"

    raw_gemini = settings.gemini_model or "gemini/gemini-3.6-flash"
    gemini_model = raw_gemini if raw_gemini.startswith("gemini/") else f"gemini/{raw_gemini}"

    # Broadcast agent debate started
    await manager.publish_event(
        debate_id=debate_id,
        event_type="agent_debate_started",
        payload={
            "agent_for": "Agent FOR",
            "agent_against": "Agent AGAINST",
            "total_rounds": 4
        }
    )

    rounds_plan = [
        (1, "OPENING", "OPENING"),
        (2, "REBUTTAL", "REBUTTAL"),
        (3, "CROSS_EXAMINATION", "QUESTION"),
        (4, "CLOSING", "CLOSING"),
    ]

    for round_num, phase_name, arg_type in rounds_plan:
        async with async_session_factory() as session:
            debate = await session.scalar(
                select(Debate)
                .options(
                    selectinload(Debate.question),
                    selectinload(Debate.sides),
                    selectinload(Debate.participants),
                    selectinload(Debate.rounds)
                )
                .where(Debate.id == uuid.UUID(debate_id))
            )
            if not debate or debate.status != DebateStatus.LIVE:
                logger.warning(f"Debate {debate_id} is not LIVE, halting agent loop.")
                return

            topic = debate.question.text if debate.question else "Resolved: The topic at hand."

            # Find FOR and AGAINST participants
            part_for = None
            part_against = None
            for p in debate.participants:
                pos = getattr(p.initial_position, 'value', p.initial_position)
                if pos == "FOR" or (hasattr(p, 'side') and getattr(p.side, 'label', None) == SideLabel.FOR):
                    part_for = p
                else:
                    part_against = p

            # If sides not labeled, default first to FOR and second to AGAINST
            if not part_for and debate.participants:
                part_for = debate.participants[0]
            if not part_against and len(debate.participants) > 1:
                part_against = debate.participants[1]

            # Fetch all past arguments to build history
            args_records = await session.scalars(
                select(Argument)
                .where(Argument.debate_id == debate.id)
                .order_by(Argument.sequence)
            )
            history_messages: List[Dict[str, str]] = []
            for a in args_records:
                role = "assistant" if a.participant_id == part_for.id else "user"
                history_messages.append({"role": role, "content": a.content})

            # Fetch current round object
            current_round_obj = await session.scalar(
                select(Round).where(Round.debate_id == debate.id, Round.round_number == round_num)
            )

        # ── Turn 1: Agent FOR (Groq) ──────────────────────────────
        groq_display_name = groq_model.replace("groq/", "")
        gemini_display_name = gemini_model.replace("gemini/", "")

        await manager.publish_event(
            debate_id=debate_id,
            event_type="agent_thinking",
            payload={"agent": "Agent FOR", "side": "FOR", "round": round_num, "phase": phase_name}
        )

        for_system = (
            f"You are a master debater arguing strictly FOR the proposition: '{topic}'.\n"
            f"Present compelling, evidence-based, concise arguments. "
            f"Do not preface with pleasantries. Speak with intellectual force and clarity."
        )

        if phase_name == "OPENING":
            for_prompt = f"Deliver your Round 1 OPENING statement FOR '{topic}'. Frame the key arguments (2-3 paragraphs)."
        elif phase_name == "REBUTTAL":
            for_prompt = f"Deliver your Round 2 REBUTTAL FOR '{topic}'. Directly counter the points made by the AGAINST side."
        elif phase_name == "CROSS_EXAMINATION":
            for_prompt = f"Deliver your Round 3 CROSS-EXAMINATION FOR '{topic}'. Challenge the core vulnerabilities and assumptions of the AGAINST position."
        else: # CLOSING
            for_prompt = f"Deliver your Round 4 FINAL CLOSING statement FOR '{topic}'. Synthesize why the FOR position decisively won this debate."

        for_content = await _generate_agent_turn(
            model=groq_model,
            api_key=settings.groq_api_key,
            system_prompt=for_system,
            conversation_history=history_messages,
            turn_instruction=for_prompt
        )

        # Save Agent FOR argument
        async with async_session_factory() as session:
            arg_for = Argument(
                debate_id=uuid.UUID(debate_id),
                round_id=current_round_obj.id if current_round_obj else None,
                participant_id=part_for.id,
                side_id=part_for.side_id,
                content=for_content,
                argument_type=arg_type,
                sequence=len(history_messages) + 1
            )
            session.add(arg_for)
            await session.commit()
            await session.refresh(arg_for)

        # Broadcast turn 1 argument
        await manager.publish_event(
            debate_id=debate_id,
            event_type="argument_submitted",
            payload={
                "id": str(arg_for.id),
                "content": arg_for.content,
                "side_id": part_for.side_id.hex,
                "side": "FOR",
                "is_ai": True,
                "agent_name": "Agent FOR",
                "type": arg_type,
                "round": round_num
            }
        )

        # Natural spectator pause
        await asyncio.sleep(2.5)

        # ── Turn 2: Agent AGAINST (Gemini) ────────────────────────
        await manager.publish_event(
            debate_id=debate_id,
            event_type="agent_thinking",
            payload={"agent": "Agent AGAINST", "side": "AGAINST", "round": round_num, "phase": phase_name}
        )

        against_system = (
            f"You are a master debater arguing strictly AGAINST the proposition: '{topic}'.\n"
            f"Dissect flaws in the opposing side's reasoning with empirical rigor. "
            f"Do not preface with pleasantries. Speak with intellectual force and clarity."
        )

        # Update history with the FOR response
        history_messages.append({"role": "user", "content": for_content})

        if phase_name == "OPENING":
            against_prompt = f"Deliver your Round 1 OPENING statement AGAINST '{topic}', reacting to FOR's opening (2-3 paragraphs)."
        elif phase_name == "REBUTTAL":
            against_prompt = f"Deliver your Round 2 REBUTTAL AGAINST '{topic}'. Dismantle the arguments just presented by FOR."
        elif phase_name == "CROSS_EXAMINATION":
            against_prompt = f"Deliver your Round 3 CROSS-EXAMINATION answer & counter-challenge AGAINST '{topic}'. Expose the fallacies of FOR."
        else: # CLOSING
            against_prompt = f"Deliver your Round 4 FINAL CLOSING statement AGAINST '{topic}'. Synthesize why the AGAINST position held the stronger ground."

        against_content = await _generate_agent_turn(
            model=gemini_model,
            api_key=settings.google_api_key,
            system_prompt=against_system,
            conversation_history=history_messages,
            turn_instruction=against_prompt
        )

        # Save Agent AGAINST argument
        async with async_session_factory() as session:
            arg_against = Argument(
                debate_id=uuid.UUID(debate_id),
                round_id=current_round_obj.id if current_round_obj else None,
                participant_id=part_against.id,
                side_id=part_against.side_id,
                content=against_content,
                argument_type=arg_type,
                sequence=len(history_messages) + 1
            )
            session.add(arg_against)
            await session.commit()
            await session.refresh(arg_against)

        # Broadcast turn 2 argument
        await manager.publish_event(
            debate_id=debate_id,
            event_type="argument_submitted",
            payload={
                "id": str(arg_against.id),
                "content": arg_against.content,
                "side_id": part_against.side_id.hex,
                "side": "AGAINST",
                "is_ai": True,
                "agent_name": "Agent AGAINST",
                "type": arg_type,
                "round": round_num
            }
        )

        # Natural spectator pause before advancing round
        await asyncio.sleep(2.0)

        # ── Advance Round in State Machine ────────────────────────
        async with async_session_factory() as session:
            debate_reload = await session.scalar(select(Debate).where(Debate.id == uuid.UUID(debate_id)))
            fsm = DebateStateMachine(session)
            next_round = await fsm.advance_round(debate_reload)
            await session.commit()

            if next_round:
                await manager.publish_event(
                    debate_id=debate_id,
                    event_type="round_advanced",
                    payload={
                        "round_number": next_round.round_number,
                        "phase": next_round.phase.value if hasattr(next_round.phase, 'value') else str(next_round.phase)
                    }
                )
                logger.info(f"Agent debate {debate_id} advanced to Round {next_round.round_number}")
            else:
                # All 4 rounds complete!
                await manager.publish_event(
                    debate_id=debate_id,
                    event_type="debate_completed",
                    payload={"debate_id": debate_id, "status": "COMPLETED"}
                )
                logger.info(f"Agent debate {debate_id} completed all 4 rounds! Triggering final verdict...")
                await generate_verdict_async(debate_id)
                return
