"""Claim ledger: extract structured claims from each turn and update statuses."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.engine.types import ClaimStatus, Round
from backend.app.llm import prompts
from backend.app.llm.gateway import LLMError, Role, complete_json
from backend.app.models import Claim, Debate, Turn
from backend.app.moderation.injection import UNTRUSTED_NOTICE, wrap
from backend.app.swarm.context import ROUND_NAMES, ledger_block

log = get_logger("provok.ledger")
MAX_CLAIMS_PER_TURN = 6

_EFFECT_STATUS = {"rebuts": ClaimStatus.REBUTTED, "concedes": ClaimStatus.CONCEDED}


async def extract_claims(db: AsyncSession, turn_id: uuid.UUID) -> list[Claim]:
    turn = await db.get(Turn, turn_id)
    if turn is None or turn.is_forfeit or not turn.content.strip():
        return []
    debate = await db.get(Debate, turn.debate_id)
    if debate is None:
        return []
    await db.refresh(debate, ["sides"])
    # Serialise ledger writes per debate so claim seq numbers never collide.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"ledger:{debate.id}"})
    already = await db.scalar(select(func.count()).select_from(Claim).where(Claim.turn_id == turn.id))
    if already:
        return []  # idempotent: this turn was processed by an earlier attempt

    side_pos = {s.id: s.position for s in debate.sides}
    existing = list((await db.scalars(select(Claim).where(Claim.debate_id == debate.id).order_by(Claim.seq))).all())
    own_pos = side_pos[turn.side_id]
    try:
        data = await complete_json(Role.LEDGER, None, [{"role": "user", "content": prompts.render(
            "ledger", question=debate.question, ledger_block=ledger_block(existing, side_pos),
            side_label=own_pos.upper(), round_name=ROUND_NAMES[Round(turn.round)], kind=turn.kind,
            turn_block=wrap(turn.content, side=own_pos.upper(), kind=turn.kind),
            untrusted_notice=UNTRUSTED_NOTICE)}], max_tokens=900, timeout=40, debate_id=debate.id)
    except LLMError as exc:
        log.warning("ledger_extract_failed", turn_id=str(turn.id), error=str(exc))
        return []

    by_seq = {c.seq: c for c in existing}
    next_seq = (max(by_seq) if by_seq else 0) + 1
    citation_urls = {c.get("url") for c in (turn.citations or [])}
    created: list[Claim] = []
    for item in (data.get("claims", []) if isinstance(data, dict) else [])[:MAX_CLAIMS_PER_TURN]:
        claim_text = str(item.get("text", "")).strip()
        if not claim_text:
            continue
        url = item.get("source_url")
        url = str(url)[:2000] if isinstance(url, str) and url.startswith(("http://", "https://")) else None
        if url and turn.source == "swarm" and url not in citation_urls:
            url = None  # AI turns may only cite what's in their research cache
        targets = [by_seq[int(s)] for s in item.get("responds_to", []) if str(s).isdigit() and int(s) in by_seq]
        effect = item.get("effect")
        claim = Claim(debate_id=debate.id, seq=next_seq, turn_id=turn.id, side_id=turn.side_id,
                      text=claim_text[:500], source_url=url,
                      responds_to_claim_id=targets[0].id if targets else None)
        next_seq += 1
        db.add(claim)
        created.append(claim)
        new_status = _EFFECT_STATUS.get(str(effect))
        for target in targets:
            if new_status and side_pos[target.side_id] != own_pos:
                target.status = new_status.value
    await db.flush()
    return created
