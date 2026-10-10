"""Credit accounting. The ledger is append-only and every entry is idempotent."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.engine.rules import Charge, InsufficientCredits
from backend.app.models import CreditLedger, Debate, User

log = get_logger("provok.credits")


async def apply_credit(db: AsyncSession, user_id: uuid.UUID, delta: int, reason: str, *, ref_id: str | None,
                       idempotency_key: str) -> int:
    """Atomically add `delta` credits. Returns the new balance. Re-applying the same key is a no-op."""
    user = await db.scalar(select(User).where(User.id == user_id).with_for_update(key_share=True))
    if user is None:
        raise ValueError("user not found")
    existing = await db.scalar(select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key))
    if existing is not None:
        return user.credits
    new_balance = user.credits + delta
    if new_balance < 0:
        raise InsufficientCredits(-delta, user.credits)
    user.credits = new_balance
    db.add(CreditLedger(user_id=user_id, delta=delta, reason=reason, ref_id=ref_id, balance_after=new_balance,
                        idempotency_key=idempotency_key))
    await db.flush()
    log.info("credits_applied", user_id=str(user_id), delta=delta, reason=reason, balance=new_balance)
    return new_balance


async def charge_for_debate(db: AsyncSession, user: User, debate: Debate, charge: Charge) -> None:
    """Called inside the debate-creation transaction; `user` must be row-locked by the caller."""
    debate.credit_cost = charge.cost
    debate.paid_with = charge.paid_with
    if charge.uses_free_debate:
        user.free_ai_debates_used += 1
    if charge.credits_to_debit:
        await apply_credit(db, user.id, -charge.credits_to_debit, "debate", ref_id=str(debate.id),
                           idempotency_key=f"debate:{debate.id}")


async def refund_debate(db: AsyncSession, debate: Debate, reason: str) -> bool:
    if debate.refunded or debate.paid_with == "none" or debate.created_by is None:
        return False
    if debate.paid_with == "credits" and debate.credit_cost > 0:
        await apply_credit(db, debate.created_by, debate.credit_cost, "refund", ref_id=str(debate.id),
                           idempotency_key=f"refund:{debate.id}")
    elif debate.paid_with == "free":
        user = await db.scalar(select(User).where(User.id == debate.created_by).with_for_update(key_share=True))
        if user is not None and user.free_ai_debates_used > 0:
            user.free_ai_debates_used -= 1
    debate.refunded = True
    log.info("debate_refunded", debate_id=str(debate.id), reason=reason, paid_with=debate.paid_with)
    return True
