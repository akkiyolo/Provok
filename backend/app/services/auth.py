"""Auth domain logic: users, sessions (refresh-token rotation), email tokens, Google identity."""
from __future__ import annotations

import re
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Conflict, Forbidden, Unauthorized
from backend.app.core.logging import get_logger
from backend.app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    utcnow,
)
from backend.app.engine.types import UserStatus
from backend.app.models import AuthSession, EmailToken, OAuthAccount, PushSubscription, User

log = get_logger("provok.auth")

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
RESERVED_USERNAMES = {
    "admin", "administrator", "root", "provok", "api", "support", "help", "system", "moderator", "mod", "staff",
    "official", "null", "undefined", "me", "settings", "login", "signup", "wallet", "new", "d", "u", "leaderboard",
    "challenges", "notifications", "search", "about", "terms", "privacy", "security", "ai", "judge", "swarm",
}
REUSE_GRACE_SECONDS = 20


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


def normalise_email(email: str) -> str:
    return email.strip().lower()


def clean_display_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")  # strip control/format chars
    return re.sub(r"\s+", " ", name).strip()[:60]


def username_problem(username: str) -> str | None:
    if not USERNAME_RE.match(username):
        return "Usernames are 3–20 characters: lowercase letters, numbers and underscores."
    if username in RESERVED_USERNAMES:
        return "That username is reserved."
    return None


async def username_taken(db: AsyncSession, username: str, *, exclude: uuid.UUID | None = None) -> bool:
    q = select(User.id).where(func.lower(User.username) == username.lower())
    if exclude:
        q = q.where(User.id != exclude)
    return (await db.scalar(q)) is not None


async def generate_username(db: AsyncSession, seed: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", unicodedata.normalize("NFKD", seed).encode("ascii", "ignore").decode().lower())
    base = (base or "debater")[:14]
    if len(base) < 3:
        base = f"{base}deb"
    candidate = base
    for _ in range(20):
        if candidate not in RESERVED_USERNAMES and not await username_taken(db, candidate):
            return candidate
        candidate = f"{base}{secrets.randbelow(10_000)}"
    return f"user{secrets.token_hex(4)}"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.email) == normalise_email(email)))


async def create_user(db: AsyncSession, *, email: str, username: str, display_name: str,
                      password: str | None, verified: bool = False, avatar_url: str | None = None) -> User:
    if await get_user_by_email(db, email):
        raise Conflict("An account with this email already exists. Try signing in.", code="email_taken")
    if await username_taken(db, username):
        raise Conflict("That username is taken.", code="username_taken")
    user = User(email=normalise_email(email), username=username, display_name=clean_display_name(display_name) or username,
                password_hash=hash_password(password) if password else None,
                email_verified_at=utcnow() if verified else None, avatar_url=avatar_url)
    db.add(user)
    await db.flush()
    return user


# ── Sessions ───────────────────────────────────────────────────────────────


async def issue_session(db: AsyncSession, user: User, *, user_agent: str | None, ip: str | None,
                        family_id: uuid.UUID | None = None) -> IssuedTokens:
    s = get_settings()
    refresh = new_opaque_token()
    db.add(AuthSession(user_id=user.id, family_id=family_id or uuid.uuid4(), token_hash=hash_token(refresh),
                       expires_at=utcnow() + timedelta(days=s.refresh_token_ttl_days),
                       user_agent=(user_agent or "")[:300] or None, ip=ip))
    user.last_login_at = utcnow()
    await db.flush()
    return IssuedTokens(create_access_token(user.id, user.token_version, user.role), refresh,
                        s.access_token_ttl_seconds)


async def rotate_session(db: AsyncSession, refresh_token: str, *, user_agent: str | None,
                         ip: str | None) -> tuple[User, IssuedTokens]:
    now = utcnow()
    sess = await db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(refresh_token))
                           .with_for_update(key_share=True))
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    if sess.rotated_at is not None:
        if (now - sess.rotated_at).total_seconds() > REUSE_GRACE_SECONDS:
            # A rotated token came back: assume theft and kill the whole lineage.
            await revoke_family(db, sess.family_id)
            log.warning("refresh_token_reuse_detected", user_id=str(sess.user_id), family_id=str(sess.family_id))
            raise Unauthorized("Your session has expired. Please sign in again.", code="session_reused")
        # Concurrent refresh from two tabs within the grace window: allow, same family.
    user = await db.get(User, sess.user_id)
    if user is None or user.status in (UserStatus.BANNED, UserStatus.DELETED):
        await revoke_family(db, sess.family_id)
        raise Unauthorized("Your session has expired. Please sign in again.", code="session_expired")
    if sess.rotated_at is None:
        sess.rotated_at = now
    tokens = await issue_session(db, user, user_agent=user_agent, ip=ip, family_id=sess.family_id)
    return user, tokens


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(update(AuthSession).where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
                     .values(revoked_at=utcnow()))


async def revoke_by_token(db: AsyncSession, refresh_token: str) -> None:
    sess = await db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(refresh_token)))
    if sess is not None:
        await revoke_family(db, sess.family_id)


async def revoke_all(db: AsyncSession, user: User) -> None:
    await db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                     .values(revoked_at=utcnow()))
    user.token_version += 1  # invalidates outstanding access tokens immediately
    # Signed-out devices stop getting pushes; the device still signed in re-subscribes on its next page load.
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id))


def set_refresh_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(s.refresh_cookie_name, token, max_age=s.refresh_token_ttl_days * 86400, httponly=True,
                        secure=s.cookie_secure, samesite="lax", path=f"{s.api_prefix}/auth",
                        domain=s.cookie_domain or None)


def clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path=f"{s.api_prefix}/auth", domain=s.cookie_domain or None,
                           secure=s.cookie_secure, httponly=True, samesite="lax")


# ── Email tokens ───────────────────────────────────────────────────────────


async def create_email_token(db: AsyncSession, user: User, purpose: str) -> str:
    s = get_settings()
    ttl = s.email_token_ttl_minutes if purpose == "verify" else s.password_reset_ttl_minutes
    # Only the newest token of a purpose is valid.
    await db.execute(update(EmailToken).where(EmailToken.user_id == user.id, EmailToken.purpose == purpose,
                                              EmailToken.used_at.is_(None)).values(used_at=utcnow()))
    token = new_opaque_token()
    db.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=hash_token(token),
                      expires_at=utcnow() + timedelta(minutes=ttl)))
    await db.flush()
    return token


async def consume_email_token(db: AsyncSession, token: str, purpose: str) -> User:
    row = await db.scalar(select(EmailToken).where(EmailToken.token_hash == hash_token(token),
                                                   EmailToken.purpose == purpose).with_for_update(key_share=True))
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise AppError("This link is invalid or has expired. Request a new one.", code="token_expired")
    row.used_at = utcnow()
    user = await db.get(User, row.user_id)
    if user is None or user.status == UserStatus.DELETED:
        raise AppError("This link is invalid or has expired.", code="token_expired")
    return user


# ── Google ─────────────────────────────────────────────────────────────────


async def login_with_google(db: AsyncSession, *, sub: str, email: str, name: str, picture: str | None) -> User:
    link = await db.scalar(select(OAuthAccount).where(OAuthAccount.provider == "google",
                                                      OAuthAccount.provider_user_id == sub))
    if link is not None:
        user = await db.get(User, link.user_id)
        if user is None or user.status == UserStatus.DELETED:
            raise Unauthorized("This account no longer exists.")
    else:
        user = await get_user_by_email(db, email)
        if user is None:
            if not await _signups_open():
                raise Forbidden("Sign-ups are paused right now. Please try again soon.", code="signups_closed")
            username = await generate_username(db, name or email.split("@")[0])
            user = await create_user(db, email=email, username=username, display_name=name or username,
                                     password=None, verified=True, avatar_url=picture)
        db.add(OAuthAccount(user_id=user.id, provider="google", provider_user_id=sub, email=email))
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()  # Google verified it
    if user.status == UserStatus.BANNED:
        raise Forbidden("This account has been suspended.", code="account_banned")
    await db.flush()
    return user


async def _signups_open() -> bool:
    from backend.app.services import flags
    return await flags.is_enabled(flags.SIGNUPS)
