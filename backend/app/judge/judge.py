"""
Judging: citation check → two blinded judge runs (A/B swapped) → aggregation →
verdict + ratings. Judges never see usernames, human/AI status or model names.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.engine.rules import elo_update
from backend.app.engine.types import ClaimStatus, ParticipantType, Position, Round
from backend.app.judge.aggregation import AggregatedVerdict, JudgeOutputError, JudgeRun, aggregate, parse_run
from backend.app.llm import prompts
from backend.app.llm.gateway import LLMError, Role, complete_json
from backend.app.llm.registry import ModelInfo, all_models, pick_judge
from backend.app.models import Claim, Debate, ModelRegistry, Turn, User, Verdict
from backend.app.moderation.injection import UNTRUSTED_NOTICE
from backend.app.services.safe_fetch import FetchBlocked, fetch_text
from backend.app.swarm.context import history_block, ledger_block

log = get_logger("provok.judge")
MAX_CITATION_CHECKS = 8
ROUND_ORDER = [r.value for r in Round]


class JudgingError(Exception):
    pass


@dataclass
class VerdictResult:
    verdict: Verdict
    aggregated: AggregatedVerdict | None


# ── Citation check ─────────────────────────────────────────────────────────


async def check_citations(db: AsyncSession, debate: Debate, claims: list[Claim], judge: ModelInfo) -> None:
    targets = [c for c in claims if c.source_url and c.status not in (
        ClaimStatus.SUPPORTED, ClaimStatus.MISATTRIBUTED, ClaimStatus.CONCEDED)][:MAX_CITATION_CHECKS]
    sem = asyncio.Semaphore(4)

    async def one(c: Claim) -> tuple[Claim, str | None]:
        async with sem:
            try:
                page = await fetch_text(c.source_url or "", max_chars=8000)
            except (FetchBlocked, Exception) as exc:  # unreachable source ⇒ we can't confirm it
                log.info("citation_fetch_failed", claim=c.seq, error=str(exc)[:120])
                return c, ClaimStatus.UNSUPPORTED.value if c.status == ClaimStatus.UNADDRESSED else None
            try:
                data = await complete_json(Role.CITATION_CHECK, judge.key, [{"role": "user", "content": prompts.render(
                    "citation_check", claim=c.text, url=c.source_url, page=page.replace("</page>", ""))}],
                    max_tokens=150, timeout=30, debate_id=debate.id)
            except LLMError:
                return c, None
            verdict = str(data.get("verdict", "")) if isinstance(data, dict) else ""
            return c, verdict if verdict in ("supported", "unsupported", "misattributed") else None

    for claim, status in await asyncio.gather(*(one(c) for c in targets)):
        # A rebuttal on the merits outranks "the source is fine"; misattribution always shows.
        if status == ClaimStatus.MISATTRIBUTED or (status and claim.status == ClaimStatus.UNADDRESSED):
            claim.status = status
    await db.flush()


# ── Blinded judging ────────────────────────────────────────────────────────


def _blind(text: str) -> str:
    return re.sub(r"\b(FOR|AGAINST)\b", "this side", text)


async def _judge_run(debate: Debate, judge: ModelInfo, turns: list[Turn], claims: list[Claim],
                     side_pos: dict[uuid.UUID, str], label_map: dict[str, str], rounds: list[str]) -> JudgeRun:
    """label_map: position -> label, e.g. {"for": "A", "against": "B"}."""
    labels = dict(label_map)
    first, second = sorted(labels.values())
    # Claims of the side labelled A are listed first in every run (order follows the label, not the position).
    ordered_claims = sorted(claims, key=lambda c: (labels[side_pos[c.side_id]], c.seq))
    prompt = prompts.render(
        "judge", question=debate.question, label_first=first, label_second=second,
        untrusted_notice=UNTRUSTED_NOTICE,
        ledger_block=_blind(ledger_block(ordered_claims, side_pos, labels=labels)),
        transcript_block=_blind(history_block(turns, side_pos, labels=labels)), rounds_list=", ".join(rounds),
    )
    data = await complete_json(Role.JUDGE, judge.key, [{"role": "user", "content": prompt}], max_tokens=3500,
                               timeout=120, temperature=0.1, debate_id=debate.id)
    label_to_position = {lab: pos for pos, lab in labels.items()}
    return parse_run(data, label_to_position, rounds)


def relabel(explanation: str, label_to_position: dict[str, str]) -> str:
    """Map blinded labels back to FOR/AGAINST. Handles "Side A", "A's" and bare letters, but leaves
    the English article "A" alone when it starts a sentence or precedes a lowercase word."""
    def name(label: str) -> str:
        return label_to_position.get(label, label).upper()

    text = re.sub(r"\bSide ([AB])\b", lambda m: name(m.group(1)), explanation)
    text = re.sub(r"\b([AB])(['’]s)\b", lambda m: name(m.group(1)) + m.group(2), text)
    text = re.sub(r"\bB\b", lambda m: name("B"), text)
    return re.sub(r"(?<![.!?]\s)(?<!^)\bA\b(?!\s+[a-z])", lambda m: name("A"), text)


async def judge_debate(db: AsyncSession, debate: Debate, attempt: int = 0) -> VerdictResult:
    existing = await db.scalar(select(Verdict).where(Verdict.debate_id == debate.id))
    if existing is not None:
        return VerdictResult(existing, None)
    settings = get_settings()
    side_pos = {s.id: s.position for s in debate.sides}
    pos_side = {s.position: s for s in debate.sides}
    turns = list((await db.scalars(select(Turn).where(Turn.debate_id == debate.id)
                                   .order_by(Turn.created_at, Turn.turn_index))).all())
    claims = list((await db.scalars(select(Claim).where(Claim.debate_id == debate.id).order_by(Claim.seq))).all())
    rounds = [r for r in ROUND_ORDER if any(t.round == r for t in turns)]

    if debate.conceded_position:
        loser = debate.conceded_position
        winner = Position(loser).other.value
        verdict = Verdict(debate_id=debate.id, winner_side_id=pos_side[winner].id, is_close=False,
                          scores={}, per_round={},
                          reasoning=f"{loser.upper()} conceded, so {winner.upper()} takes the debate.",
                          judge_runs=[], judge_model_key=None)
        db.add(verdict)
        await db.flush()
        await _update_ratings(db, debate, winner)
        return VerdictResult(verdict, None)

    if not rounds or all(t.is_forfeit for t in turns):
        verdict = Verdict(debate_id=debate.id, winner_side_id=None, is_close=True, scores={}, per_round={},
                          reasoning="Neither side made an argument, so there's nothing to judge.",
                          judge_runs=[], judge_model_key=None)
        db.add(verdict)
        await db.flush()
        return VerdictResult(verdict, None)

    # Walkover: a side that let every turn run out can't out-argue one that showed up, whatever a judge says.
    silent = [p for p in ("for", "against") if all(t.is_forfeit for t in turns if side_pos[t.side_id] == p)]
    if len(silent) == 1:
        loser = silent[0]
        winner = Position(loser).other.value
        verdict = Verdict(debate_id=debate.id, winner_side_id=pos_side[winner].id, is_close=False,
                          scores={}, per_round={},
                          reasoning=f"{loser.upper()} didn't make an argument, so {winner.upper()} takes the debate.",
                          judge_runs=[], judge_model_key=None)
        db.add(verdict)
        await db.flush()
        await _update_ratings(db, debate, winner)
        return VerdictResult(verdict, None)

    models = await all_models()
    debater_providers = {models[s.swarm_config["model_key"]].provider for s in debate.sides
                         if s.swarm_config and s.swarm_config.get("model_key") in models}
    judge = await pick_judge(debater_providers, attempt)
    if judge is None:
        raise JudgingError("No judge model is enabled")

    await check_citations(db, debate, claims, judge)

    async def run_with_retry(label_map: dict[str, str]) -> JudgeRun | None:
        for attempt in range(2):
            try:
                return await _judge_run(debate, judge, turns, claims, side_pos, label_map, rounds)
            except (LLMError, JudgeOutputError) as exc:
                log.warning("judge_run_failed", debate_id=str(debate.id), attempt=attempt, error=str(exc))
        return None

    run_a, run_b = await asyncio.gather(run_with_retry({"for": "A", "against": "B"}),
                                        run_with_retry({"for": "B", "against": "A"}))
    runs = [r for r in (run_a, run_b) if r is not None]
    if not runs:
        raise JudgingError("Both judge runs failed")
    agg = aggregate(runs, close_margin=settings.close_margin)
    if len(runs) == 1:
        agg = AggregatedVerdict(agg.winner, True, agg.totals, agg.per_round, agg.margin, False)

    explain_run = next((r for r in runs if r.winner_position == agg.winner), runs[0])
    seq_to_id = {c.seq: str(c.id) for c in claims}
    verdict = Verdict(
        debate_id=debate.id,
        winner_side_id=pos_side[agg.winner].id if agg.winner else None,
        is_close=agg.is_close,
        scores={"for": agg.totals["for"], "against": agg.totals["against"], "margin": agg.margin,
                "runs_agree": agg.runs_agree},
        per_round=agg.per_round,
        reasoning=(relabel(explain_run.explanation, explain_run.label_to_position)[:2000]
                   or "The judge did not provide reasons."),
        decisive_claim_ids=[seq_to_id[s] for s in explain_run.decisive_claims if s in seq_to_id],
        judge_runs=[{"label_to_position": r.label_to_position, "scores": r.scores, "winner_label": r.winner_label,
                     "explanation": r.explanation} for r in runs],
        judge_model_key=judge.key,
    )
    db.add(verdict)
    await db.flush()
    await _update_ratings(db, debate, agg.winner)
    return VerdictResult(verdict, agg)


# ── Ratings ────────────────────────────────────────────────────────────────


async def _update_ratings(db: AsyncSession, debate: Debate, winner: str | None) -> None:
    k = get_settings().elo_k_factor
    sides = {s.position: s for s in debate.sides}
    entities: dict[str, Any] = {}
    for pos, side in sides.items():
        if side.participant_type == ParticipantType.HUMAN and side.user_id:
            entities[pos] = await db.scalar(select(User).where(User.id == side.user_id).with_for_update(key_share=True))
        elif side.swarm_config:
            entities[pos] = await db.scalar(select(ModelRegistry).where(
                ModelRegistry.key == side.swarm_config.get("model_key")).with_for_update(key_share=True))
    a, b = entities.get("for"), entities.get("against")
    if a is None or b is None or a is b:
        return
    score_for = 0.5 if winner is None else (1.0 if winner == "for" else 0.0)
    a.rating, b.rating = elo_update(a.rating, b.rating, score_for, k)
    for ent, score in ((a, score_for), (b, 1 - score_for)):
        if isinstance(ent, User):
            if score == 1:
                ent.wins += 1
            elif score == 0:
                ent.losses += 1
            else:
                ent.draws += 1
    await db.flush()
