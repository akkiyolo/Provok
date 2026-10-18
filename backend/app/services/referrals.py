"""Referrals: invite links, attributing new accounts, and paying both sides once the newcomer verifies their email.

A visit to /r/<code> leaves a `provok_ref` cookie (set by the web app); account creation (email or Google) reads it.
Rewards are credit-ledger grants with per-referral idempotency keys, so settling twice can never pay twice.
"""
from __future__ import annotations

import re
import secrets
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.engine.types import UserStatus
from backend.app.models import CreditLedger, User
from backend.app.payments.credits import apply_credit
from backend.app.services.notify import notify
from backend.app.services.outbox import Outbox

log = get_logger("provok.referrals")

COOKIE = "provok_ref"
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i
_CODE_RE = re.compile(rf"^[{_ALPHABET}]{{8}}$")
_INVITER_KEY = "referral-inviter:"
_INVITEE_KEY = "referral-invitee:"


def valid_code(code: str | None) -> bool:
    return bool(code) and bool(_CODE_RE.match(code or ""))


def canonical_email(email: str) -> str:
    """The mailbox behind an address: drops +tags everywhere, and dots for Gmail (which ignores them)."""
    local, _, domain = email.strip().lower().partition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local, domain = local.replace(".", ""), "gmail.com"
    return f"{local}@{domain}"


async def ensure_code(db: AsyncSession, user: User) -> str:
    if user.referral_code:
        return user.referral_code
    for _ in range(10):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if await db.scalar(select(User.id).where(User.referral_code == code)) is None:
            user.referral_code = code
            await db.flush()
            return code
    raise RuntimeError("could not allocate a referral code")


async def inviter_for_code(db: AsyncSession, code: str | None) -> User | None:
    if not valid_code(code):
        return None
    inviter = await db.scalar(select(User).where(User.referral_code == code))
    if inviter is None or inviter.status != UserStatus.ACTIVE:
        return None
    return inviter


async def attach(db: AsyncSession, user: User, code: str | None) -> None:
    """At account creation only: remember who invited this person."""
    if not get_settings().referral_enabled or user.referred_by_id is not None:
        return
    inviter = await inviter_for_code(db, code)
    if inviter is None or inviter.id == user.id:
        return
    user.referred_by_id = inviter.id
    await db.flush()


async def inviter_rewards(db: AsyncSession, inviter_id) -> int:
    return await db.scalar(select(func.count()).select_from(CreditLedger).where(
        CreditLedger.user_id == inviter_id, CreditLedger.idempotency_key.like(f"{_INVITER_KEY}%"))) or 0


async def settle(db: AsyncSession, outbox: Outbox, user: User) -> None:
    """Once the invited person has a verified email: credit both sides (inviter up to the cap). Runs once."""
    s = get_settings()
    if not s.referral_enabled or user.referred_by_id is None or user.referral_settled_at is not None \
            or user.email_verified_at is None:
        return
    user.referral_settled_at = utcnow()
    # Lock the inviter first so two friends verifying at once can't both slip under the cap.
    inviter = await db.scalar(select(User).where(User.id == user.referred_by_id).with_for_update(key_share=True))
    if inviter is None or inviter.status != UserStatus.ACTIVE:
        await db.flush()
        return
    if canonical_email(inviter.email) == canonical_email(user.email):
        log.info("referral_self", inviter=str(inviter.id), invitee=str(user.id))
        await db.flush()
        return
    if s.referral_invitee_credits > 0:
        await apply_credit(db, user.id, s.referral_invitee_credits, "grant", ref_id=f"referral:{inviter.id}",
                           idempotency_key=f"{_INVITEE_KEY}{user.id}")
    paid_inviter = 0
    if s.referral_inviter_credits > 0 and await inviter_rewards(db, inviter.id) < s.referral_max_rewards_per_user:
        await apply_credit(db, inviter.id, s.referral_inviter_credits, "grant", ref_id=f"referral:{user.id}",
                           idempotency_key=f"{_INVITER_KEY}{user.id}")
        paid_inviter = s.referral_inviter_credits
    body = (f"You earned {paid_inviter} credit{'s' if paid_inviter != 1 else ''} for the invite."
            if paid_inviter else "Thanks for spreading the word.")
    await notify(db, outbox, inviter.id, "referral", f"{user.display_name} joined Provok with your invite",
                 body=body, link="/invite")
    log.info("referral_settled", inviter=str(inviter.id), invitee=str(user.id), inviter_credits=paid_inviter)


async def summary(db: AsyncSession, user: User) -> dict[str, Any]:
    s = get_settings()
    code = await ensure_code(db, user)
    invited = (await db.scalars(
        select(User).where(User.referred_by_id == user.id, User.status != UserStatus.DELETED)
        .order_by(User.created_at.desc()).limit(50)
    )).all()
    rewarded = await inviter_rewards(db, user.id)
    return {
        "enabled": s.referral_enabled,
        "code": code,
        "link": f"{s.web_url.rstrip('/')}/r/{code}",
        "inviter_credits": s.referral_inviter_credits,
        "invitee_credits": s.referral_invitee_credits,
        "max_rewards": s.referral_max_rewards_per_user,
        "rewarded": rewarded,
        "invited": [{"username": u.username, "display_name": u.display_name, "avatar_url": u.avatar_url,
                     "joined_at": u.created_at, "verified": u.email_verified_at is not None} for u in invited],
    }
