"""Shared FastAPI dependencies: DB session, current user, role/verification gates."""
from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import Forbidden, Unauthorized
from backend.app.core.ratelimit import client_ip, enforce
from backend.app.core.security import decode_jwt
from backend.app.db.session import get_db
from backend.app.engine.types import UserStatus
from backend.app.models import User

DB = Annotated[AsyncSession, Depends(get_db)]


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def _user_from_token(db: AsyncSession, token: str) -> User:
    try:
        payload = decode_jwt(token, "access")
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise Unauthorized("Your session has expired. Please sign in again.", code="token_invalid") from exc
    user = await db.get(User, user_id)
    if user is None or user.status == UserStatus.DELETED or payload.get("ver") != user.token_version:
        raise Unauthorized("Your session has expired. Please sign in again.", code="token_invalid")
    if user.status == UserStatus.BANNED:
        raise Forbidden("This account has been suspended.", code="account_banned")
    return user


async def current_user(request: Request, db: DB) -> User:
    token = _bearer(request)
    if not token:
        raise Unauthorized("Sign in to continue.", code="auth_required")
    user = await _user_from_token(db, token)
    request.state.user_id = str(user.id)
    return user


async def optional_user(request: Request, db: DB) -> User | None:
    token = _bearer(request)
    if not token:
        return None
    try:
        return await _user_from_token(db, token)
    except (Unauthorized, Forbidden):
        return None


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]


async def verified_user(user: CurrentUser) -> User:
    if get_settings().require_verified_email_to_debate and user.email_verified_at is None:
        raise Forbidden("Confirm your email to do that. Check your inbox for the link.", code="email_unverified")
    return user


VerifiedUser = Annotated[User, Depends(verified_user)]


async def active_debater(user: VerifiedUser) -> User:
    if user.status == UserStatus.RESTRICTED:
        raise Forbidden("Your account can watch and vote, but can't debate right now.", code="account_restricted")
    return user


ActiveDebater = Annotated[User, Depends(active_debater)]


async def admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise Forbidden("Admins only.")
    return user


AdminUser = Annotated[User, Depends(admin_user)]


def rate_limit(bucket: str, spec_attr: str, *, by: str = "ip"):
    """Dependency factory: `Depends(rate_limit("login", "rl_login_ip"))`."""
    async def _dep(request: Request) -> None:
        spec = getattr(get_settings(), spec_attr)
        identity = client_ip(request) if by == "ip" else getattr(request.state, "user_id", None) or client_ip(request)
        await enforce(bucket, identity, spec)
    return Depends(_dep)
