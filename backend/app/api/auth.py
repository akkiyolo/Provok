"""Auth routes: email/password, refresh rotation, email verification, password reset, Google OAuth."""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from backend.app.api.deps import DB, CurrentUser, rate_limit
from backend.app.core.config import get_settings
from backend.app.core.errors import AppError, Forbidden, ServiceUnavailable, Unauthorized
from backend.app.core.logging import get_logger
from backend.app.core.ratelimit import client_ip, enforce, reset
from backend.app.core.security import (
    create_jwt,
    decode_jwt,
    hash_password,
    password_needs_rehash,
    password_problem,
    utcnow,
    verify_password,
)
from backend.app.engine.types import UserStatus
from backend.app.models import AnalyticsEvent, User
from backend.app.services import auth as svc
from backend.app.services import email as mail
from backend.app.services import flags

router = APIRouter()
log = get_logger("provok.api.auth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_google_jwks: jwt.PyJWKClient | None = None


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=40)
    display_name: str | None = Field(default=None, max_length=80)
    # Where the verification link should bring them back to (e.g. the invite they signed up from).
    next: str | None = Field(default=None, max_length=300)


class NextIn(BaseModel):
    next: str | None = Field(default=None, max_length=300)


class LoginIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=320, description="Email or username")
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(default="", max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def me_payload(user) -> dict:
    s = get_settings()
    return {
        "id": str(user.id), "email": user.email, "email_verified": user.email_verified_at is not None,
        "username": user.username, "display_name": user.display_name, "avatar_url": user.avatar_url,
        "bio": user.bio, "role": user.role, "status": user.status, "rating": user.rating,
        "wins": user.wins, "losses": user.losses, "draws": user.draws, "credits": user.credits,
        "free_ai_debates_left": max(0, s.free_ai_debates - user.free_ai_debates_used),
        "has_password": user.password_hash is not None, "onboarded": user.onboarded,
        "banner_url": user.banner_url, "website": user.website, "location": user.location,
        "email_notifications": user.email_notifications,
        "created_at": user.created_at,
    }


def _origin_ok(request: Request) -> None:
    """Defence in depth for cookie-authenticated endpoints: reject cross-site browser requests."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in get_settings().cors_origin_list:
        raise Forbidden("Cross-site request blocked.", code="bad_origin")


async def _tokens_response(response: Response, tokens: svc.IssuedTokens, user) -> TokenOut:
    svc.set_refresh_cookie(response, tokens.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return TokenOut(access_token=tokens.access_token, expires_in=tokens.expires_in, user=me_payload(user))


@router.post("/register", response_model=TokenOut, status_code=201,
             dependencies=[rate_limit("signup", "rl_signup_ip")])
async def register(body: RegisterIn, request: Request, response: Response, db: DB) -> TokenOut:
    _origin_ok(request)
    if not await flags.is_enabled(flags.SIGNUPS):
        raise Forbidden("Sign-ups are paused right now. Please try again soon.", code="signups_closed")
    username = body.username.strip().lower()
    if problem := svc.username_problem(username):
        raise AppError(problem, code="invalid_username", status_code=422)
    if problem := password_problem(body.password, email=body.email, username=username):
        raise AppError(problem, code="weak_password", status_code=422)
    user = await svc.create_user(db, email=body.email, username=username,
                                 display_name=body.display_name or username, password=body.password)
    token = await svc.create_email_token(db, user, "verify")
    tokens = await svc.issue_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    db.add(AnalyticsEvent(name="signup", user_id=user.id, props={"method": "password"}))
    await db.commit()
    await mail.send_verification(user.email, user.display_name, token, next_path=_safe_next(body.next))
    return await _tokens_response(response, tokens, user)


@router.post("/login", response_model=TokenOut, dependencies=[rate_limit("login_ip", "rl_login_ip")])
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> TokenOut:
    _origin_ok(request)
    ident = body.identifier.strip().lower()
    await enforce("login_account", ident, get_settings().rl_login_account,
                  "Too many sign-in attempts for this account. Try again in a few minutes, or reset your password.")
    if "@" in ident:
        user = await svc.get_user_by_email(db, ident)
    else:
        user = await db.scalar(select(User).where(func.lower(User.username) == ident))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not user or not ok or user.status == UserStatus.DELETED:
        raise Unauthorized("That email/username and password don't match.", code="invalid_credentials")
    if user.status == UserStatus.BANNED:
        raise Forbidden("This account has been suspended.", code="account_banned")
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    await reset("login_account", ident)
    tokens = await svc.issue_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    await db.commit()
    return await _tokens_response(response, tokens, user)


@router.post("/refresh", response_model=TokenOut, responses={204: {"description": "No session (signed out)"}})
async def refresh(request: Request, response: Response, db: DB) -> TokenOut | Response:
    _origin_ok(request)
    cookie = request.cookies.get(get_settings().refresh_cookie_name)
    if not cookie:
        # Every signed-out page load checks for a session; "there is none" is an answer, not an error
        # (a 401 here put a red console error on every visit). Bad or stolen cookies still get 401.
        return Response(status_code=204)
    try:
        user, tokens = await svc.rotate_session(db, cookie, user_agent=request.headers.get("user-agent"),
                                                ip=client_ip(request))
    except Unauthorized:
        await db.commit()  # persist family revocation on reuse
        svc.clear_refresh_cookie(response)
        raise
    await db.commit()
    return await _tokens_response(response, tokens, user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> Response:
    _origin_ok(request)
    cookie = request.cookies.get(get_settings().refresh_cookie_name)
    if cookie:
        await svc.revoke_by_token(db, cookie)
        await db.commit()
    out = Response(status_code=204)
    svc.clear_refresh_cookie(out)
    return out


@router.post("/logout-all", status_code=204)
async def logout_all(user: CurrentUser, db: DB) -> Response:
    await svc.revoke_all(db, user)
    await db.commit()
    out = Response(status_code=204)
    svc.clear_refresh_cookie(out)
    return out


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return me_payload(user)


@router.post("/ws-ticket")
async def ws_ticket(user: CurrentUser) -> dict:
    """Short-lived ticket for authenticating a websocket (browsers can't set headers on WS)."""
    return {"ticket": create_jwt(user.id, "ws", get_settings().ws_ticket_ttl_seconds)}


@router.post("/verify-email")
async def verify_email(body: TokenIn, db: DB) -> dict:
    user = await svc.consume_email_token(db, body.token, "verify")
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    await db.commit()
    return {"ok": True, "user": me_payload(user)}


@router.post("/resend-verification")
async def resend_verification(user: CurrentUser, request: Request, db: DB, body: NextIn | None = None) -> dict:
    if user.email_verified_at is not None:
        return {"ok": True, "already_verified": True}
    await enforce("resend_verify", str(user.id), "3/3600")
    token = await svc.create_email_token(db, user, "verify")
    await db.commit()
    await mail.send_verification(user.email, user.display_name, token, next_path=_safe_next(body.next if body else None))
    return {"ok": True}


@router.post("/forgot-password", dependencies=[rate_limit("pw_reset_ip", "rl_password_reset")])
async def forgot_password(body: EmailIn, db: DB) -> dict:
    # Same response whether or not the account exists (no account enumeration).
    email = svc.normalise_email(body.email)
    await enforce("pw_reset_email", email, get_settings().rl_password_reset)
    user = await svc.get_user_by_email(db, email)
    if user and user.status not in (UserStatus.DELETED, UserStatus.BANNED):
        token = await svc.create_email_token(db, user, "reset")
        await db.commit()
        await mail.send_password_reset(user.email, token)
    return {"ok": True, "message": "If an account exists for that email, a reset link is on its way."}


@router.post("/reset-password")
async def reset_password(body: ResetIn, db: DB) -> dict:
    user = await svc.consume_email_token(db, body.token, "reset")
    if problem := password_problem(body.password, email=user.email, username=user.username):
        raise AppError(problem, code="weak_password", status_code=422)
    user.password_hash = hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()  # they proved control of the inbox
    await svc.revoke_all(db, user)
    await db.commit()
    return {"ok": True}


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: CurrentUser, request: Request, response: Response,
                          db: DB) -> TokenOut:
    await enforce("change_pw", str(user.id), "5/3600")
    if user.password_hash and not verify_password(body.current_password, user.password_hash):
        raise AppError("Your current password is incorrect.", code="invalid_credentials", status_code=400)
    if problem := password_problem(body.new_password, email=user.email, username=user.username):
        raise AppError(problem, code="weak_password", status_code=422)
    user.password_hash = hash_password(body.new_password)
    await svc.revoke_all(db, user)  # sign out every other device
    tokens = await svc.issue_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    await db.commit()
    return await _tokens_response(response, tokens, user)


# ── Google OAuth (authorization code + PKCE + nonce) ───────────────────────


def _safe_next(next_path: str | None) -> str:
    if not next_path or not next_path.startswith("/") or next_path.startswith("//") or "\\" in next_path:
        return "/"
    return next_path[:300]


def _redirect_uri() -> str:
    s = get_settings()
    return f"{s.web_url.rstrip('/')}{s.api_prefix}/auth/google/callback"


@router.get("/google/start")
async def google_start(next: str | None = Query(default=None)) -> RedirectResponse:
    s = get_settings()
    if not s.google_oauth_enabled:
        raise ServiceUnavailable("Google sign-in isn't configured.", code="google_disabled")
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"client_id": s.google_client_id, "redirect_uri": _redirect_uri(), "response_type": "code",
              "scope": "openid email profile", "state": state, "nonce": nonce, "code_challenge": challenge,
              "code_challenge_method": "S256"}  # no prompt: returning users skip Google's account picker
    resp = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    cookie = create_jwt("google", "oauth_state", 600,
                        {"state": state, "nonce": nonce, "verifier": verifier, "next": _safe_next(next)})
    resp.set_cookie("provok_oauth", cookie, max_age=600, httponly=True, secure=s.cookie_secure, samesite="lax",
                    path=f"{s.api_prefix}/auth/google")
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, db: DB, code: str | None = None, state: str | None = None,
                          error: str | None = None) -> RedirectResponse:
    s = get_settings()
    fail = RedirectResponse(f"{s.web_url}/login?error=google", status_code=302)
    fail.delete_cookie("provok_oauth", path=f"{s.api_prefix}/auth/google")
    raw = request.cookies.get("provok_oauth")
    if error or not code or not state or not raw:
        return fail
    try:
        st = decode_jwt(raw, "oauth_state")
    except jwt.PyJWTError:
        return fail
    if not secrets.compare_digest(st.get("state", ""), state):
        return fail
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                "redirect_uri": _redirect_uri(), "grant_type": "authorization_code", "code_verifier": st["verifier"]})
            tok.raise_for_status()
            id_token = tok.json()["id_token"]
        global _google_jwks
        if _google_jwks is None:
            _google_jwks = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
        key = _google_jwks.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=s.google_client_id,
                            issuer=["https://accounts.google.com", "accounts.google.com"], leeway=30)
    except Exception as exc:
        log.warning("google_oauth_failed", error=str(exc)[:200])
        return fail
    if claims.get("nonce") != st.get("nonce") or not claims.get("email_verified") or not claims.get("email"):
        return fail
    try:
        user = await svc.login_with_google(db, sub=str(claims["sub"]), email=claims["email"],
                                           name=claims.get("name") or "", picture=claims.get("picture"))
    except (Forbidden, Unauthorized) as exc:
        return RedirectResponse(f"{s.web_url}/login?error={exc.code}", status_code=302)
    tokens = await svc.issue_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request))
    await db.commit()
    # Straight back to where the user was: the app restores the session from the refresh cookie on every load,
    # so an intermediate /auth/callback page only added a page load.
    resp = RedirectResponse(f"{s.web_url}{_safe_next(st.get('next'))}", status_code=302)
    svc.set_refresh_cookie(resp, tokens.refresh_token)
    resp.delete_cookie("provok_oauth", path=f"{s.api_prefix}/auth/google")
    return resp
