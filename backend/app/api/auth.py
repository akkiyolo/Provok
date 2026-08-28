"""PROVOK — Auth API routes (Phase 2)."""
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, or_
from typing import Any
import httpx

from backend.app.dependencies import DbSession, get_current_user, AppSettings
from backend.app.schemas.auth import UserCreate, UserResponse, Token
from backend.app.models.user import User, OAuthAccount
from backend.app.auth.security import get_password_hash, verify_password, create_access_token

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register(user_in: UserCreate, db: DbSession) -> Any:
    """User registration."""
    # Check if user exists
    stmt = select(User).where(or_(User.email == user_in.email, User.username == user_in.username))
    existing_user = await db.scalar(stmt)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="The user with this username or email already exists in the system.",
        )
    
    user = User(
        email=user_in.email,
        username=user_in.username,
        password_hash=get_password_hash(user_in.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    db: DbSession,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Any:
    """User login."""
    stmt = select(User).where(User.email == form_data.username)
    user = await db.scalar(stmt)
    if not user or not user.password_hash:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(response: Response):
    """User logout."""
    return {"message": "Logged out successfully"}

@router.post("/refresh", response_model=Token)
async def refresh(
    db: DbSession,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Refresh access token."""
    return {
        "access_token": create_access_token(current_user.id),
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)) -> Any:
    """Get current user."""
    return current_user


@router.get("/google")
async def google_login(settings: AppSettings):
    """Redirect to Google OAuth."""
    # Minimal implementation for Google OAuth redirect
    client_id = settings.google_client_id
    redirect_uri = f"{settings.api_base_url}/auth/google/callback"
    url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=openid%20email%20profile"
    return {"url": url}


@router.get("/google/callback")
async def google_callback(code: str, db: DbSession, settings: AppSettings):
    """Google OAuth callback."""
    # Simplified Google callback implementation for Phase 2
    return {"message": "Google callback placeholder. Would exchange code for token here."}

