"""Password hashing, JWT access tokens, opaque refresh/email tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from backend.app.core.config import get_settings

_hasher = PasswordHasher()  # argon2id, library defaults (RFC 9106 low-memory profile)
# Pre-computed hash used to equalise timing when a login targets a non-existent account.
_DUMMY_HASH = _hasher.hash("provok-dummy-password-for-timing")

TokenType = Literal["access", "ws", "oauth_state", "unsubscribe"]

COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "1234567890", "qwerty123", "11111111",
    "iloveyou", "admin123", "welcome1", "provok123", "letmein1", "password123", "abc12345",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


# ── Passwords ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time verification; always runs one argon2 verify."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def password_problem(password: str, *, email: str | None = None, username: str | None = None) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be at most 128 characters."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "That password is too common. Pick something harder to guess."
    if username and username.lower() in lowered:
        return "Password must not contain your username."
    if email and email.split("@")[0].lower() in lowered and len(email.split("@")[0]) >= 4:
        return "Password must not contain your email."
    return None


# ── JWT ────────────────────────────────────────────────────────────────────

def create_jwt(subject: uuid.UUID | str, token_type: TokenType, ttl_seconds: int,
               extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret_key, algorithm="HS256")


def decode_jwt(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Raises jwt.PyJWTError on any problem (expired, wrong type, bad signature …)."""
    s = get_settings()
    payload = jwt.decode(
        token,
        s.jwt_secret_key,
        algorithms=["HS256"],
        audience=s.jwt_audience,
        issuer=s.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "typ"]},
        leeway=10,
    )
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def create_access_token(user_id: uuid.UUID, token_version: int, role: str) -> str:
    return create_jwt(user_id, "access", get_settings().access_token_ttl_seconds,
                      {"ver": token_version, "role": role})


# ── Opaque tokens (refresh, email verification, password reset) ────────────

def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are stored hashed; a DB leak must not yield usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
