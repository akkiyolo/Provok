"""
PROVOK — FastAPI Dependencies.

Shared dependency injection for routes.
"""
from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings, get_settings
from backend.app.database.core import get_db
from backend.app.models.user import User
from backend.app.schemas.auth import TokenPayload

# Database session
DbSession = Annotated[AsyncSession, Depends(get_db)]

# Settings
AppSettings = Annotated[Settings, Depends(get_settings)]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/api/v1/auth/login")


async def get_redis(request: Request):
    """Get the Redis client from app state."""
    return request.app.state.redis


async def get_current_user(
    db: DbSession,
    settings: AppSettings,
    token: str = Depends(oauth2_scheme),
) -> User:
    """Validate token and return current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        token_data = TokenPayload(**payload)
        if token_data.sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.scalar(select(User).where(User.id == token_data.sub))
    if user is None:
        raise credentials_exception
    return user


async def get_current_user_optional(
    db: DbSession,
    settings: AppSettings,
    request: Request,
) -> User | None:
    """Validate token and return current user if present, else None."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        token_data = TokenPayload(**payload)
        if token_data.sub:
            user = await db.scalar(select(User).where(User.id == token_data.sub))
            return user
    except Exception:
        pass
    return None


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the user is active."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
