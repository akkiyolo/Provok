"""Auth flows end to end."""
from __future__ import annotations

import re
from datetime import timedelta

import pytest
from sqlalchemy import update

from backend.app.db.session import SessionFactory
from backend.app.models import AuthSession
from backend.app.services.email import sent_emails

API = "/api/v1/auth"


async def register(client, username="alice", password="correct-horse-battery", email=None):
    return await client.post(f"{API}/register", json={"email": email or f"{username}@example.com",
                                                       "password": password, "username": username})


def token_from_last_email() -> str:
    m = re.search(r"token=([A-Za-z0-9_\-]+)", sent_emails()[-1]["text"])
    assert m
    return m.group(1)


async def test_register_issues_tokens_cookie_and_verification_email(client):
    r = await register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"] and body["user"]["username"] == "alice"
    assert body["user"]["email_verified"] is False
    assert "provok_rt" in r.cookies
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie and "path=/api/v1/auth" in set_cookie
    assert sent_emails() and "Confirm" in sent_emails()[-1]["subject"]


@pytest.mark.parametrize("username,password,code", [
    ("ab", "correct-horse-battery", "invalid_username"),
    ("Bad Name", "correct-horse-battery", "invalid_username"),
    ("admin", "correct-horse-battery", "invalid_username"),
    ("bob", "short", "weak_password"),
    ("bob", "password123", "weak_password"),
    ("bobby", "bobby-is-great-123", "weak_password"),
])
async def test_register_validation(client, username, password, code):
    r = await register(client, username, password, email="x@example.com")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code


async def test_duplicate_email_and_username(client):
    assert (await register(client)).status_code == 201
    r = await register(client, "alice2", email="ALICE@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    r = await register(client, "alice", email="other@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "username_taken"


async def test_login_with_email_or_username_and_generic_errors(client):
    await register(client)
    for ident in ("alice@example.com", "ALICE", "alice"):
        r = await client.post(f"{API}/login", json={"identifier": ident, "password": "correct-horse-battery"})
        assert r.status_code == 200, r.text
    bad = await client.post(f"{API}/login", json={"identifier": "alice", "password": "nope-nope-nope"})
    missing = await client.post(f"{API}/login", json={"identifier": "ghost", "password": "nope-nope-nope"})
    assert bad.status_code == missing.status_code == 401
    assert bad.json()["error"]["message"] == missing.json()["error"]["message"]  # no account enumeration


async def test_me_requires_valid_token(client):
    r = await register(client)
    token = r.json()["access_token"]
    assert (await client.get(f"{API}/me")).status_code == 401
    assert (await client.get(f"{API}/me", headers={"Authorization": "Bearer junk"})).status_code == 401
    me = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["free_ai_debates_left"] == 3


async def test_refresh_rotates_and_detects_reuse(client):
    await register(client)
    first_cookie = client.cookies.get("provok_rt")
    r = await client.post(f"{API}/refresh")
    assert r.status_code == 200
    second_cookie = client.cookies.get("provok_rt")
    assert second_cookie and second_cookie != first_cookie

    # Pretend the first token was rotated long ago, then replay it (stolen token).
    async with SessionFactory() as db:
        await db.execute(update(AuthSession).where(AuthSession.rotated_at.is_not(None))
                         .values(rotated_at=AuthSession.rotated_at - timedelta(minutes=5)))
        await db.commit()
    client.cookies.set("provok_rt", first_cookie, path="/api/v1/auth")
    replay = await client.post(f"{API}/refresh")
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "session_reused"
    # The whole family is now dead — including the legitimately rotated token.
    client.cookies.set("provok_rt", second_cookie, path="/api/v1/auth")
    assert (await client.post(f"{API}/refresh")).status_code == 401


async def test_concurrent_refresh_within_grace_is_allowed(client):
    await register(client)
    cookie = client.cookies.get("provok_rt")
    assert (await client.post(f"{API}/refresh")).status_code == 200
    client.cookies.set("provok_rt", cookie, path="/api/v1/auth")
    assert (await client.post(f"{API}/refresh")).status_code == 200  # second tab, same instant


async def test_refresh_rejects_cross_site_origin(client):
    await register(client)
    r = await client.post(f"{API}/refresh", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


async def test_logout_revokes_session(client):
    await register(client)
    cookie = client.cookies.get("provok_rt")
    assert (await client.post(f"{API}/logout")).status_code == 204
    client.cookies.set("provok_rt", cookie, path="/api/v1/auth")
    assert (await client.post(f"{API}/refresh")).status_code == 401


async def test_email_verification_flow(client):
    r = await register(client)
    token = token_from_last_email()
    v = await client.post(f"{API}/verify-email", json={"token": token})
    assert v.status_code == 200 and v.json()["user"]["email_verified"] is True
    again = await client.post(f"{API}/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["error"]["code"] == "token_expired"
    assert r.status_code == 201


async def test_password_reset_flow_revokes_sessions(client):
    r = await register(client)
    old_access = r.json()["access_token"]
    old_cookie = client.cookies.get("provok_rt")
    resp = await client.post(f"{API}/forgot-password", json={"email": "alice@example.com"})
    unknown = await client.post(f"{API}/forgot-password", json={"email": "nobody@example.com"})
    assert resp.json() == unknown.json()  # identical response either way
    token = token_from_last_email()
    assert (await client.post(f"{API}/reset-password", json={"token": token, "password": "a-brand-new-passphrase"})
            ).status_code == 200
    assert (await client.get(f"{API}/me", headers={"Authorization": f"Bearer {old_access}"})).status_code == 401
    client.cookies.set("provok_rt", old_cookie, path="/api/v1/auth")
    assert (await client.post(f"{API}/refresh")).status_code == 401
    ok = await client.post(f"{API}/login", json={"identifier": "alice", "password": "a-brand-new-passphrase"})
    assert ok.status_code == 200 and ok.json()["user"]["email_verified"] is True


async def test_change_password_signs_out_other_devices(client):
    r = await register(client)
    old_access = r.json()["access_token"]
    h = {"Authorization": f"Bearer {old_access}"}
    bad = await client.post(f"{API}/change-password", headers=h,
                            json={"current_password": "wrong", "new_password": "another-good-passphrase"})
    assert bad.status_code == 400
    ok = await client.post(f"{API}/change-password", headers=h,
                           json={"current_password": "correct-horse-battery", "new_password": "another-good-passphrase"})
    assert ok.status_code == 200
    assert (await client.get(f"{API}/me", headers=h)).status_code == 401
    new_h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert (await client.get(f"{API}/me", headers=new_h)).status_code == 200


async def test_login_rate_limited_per_account(client):
    await register(client)
    codes = []
    for _ in range(10):
        r = await client.post(f"{API}/login", json={"identifier": "alice", "password": "wrong-password-x"})
        codes.append(r.status_code)
    assert 429 in codes
    assert codes[0] == 401


async def test_ws_ticket(client):
    r = await register(client)
    t = await client.post(f"{API}/ws-ticket", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert t.status_code == 200 and len(t.json()["ticket"]) > 40


async def test_google_start_requires_config(client):
    r = await client.get(f"{API}/google/start", follow_redirects=False)
    assert r.status_code == 503
