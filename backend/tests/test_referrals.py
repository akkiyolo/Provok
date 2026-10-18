"""Referrals: invite codes, attribution at sign-up (email and Google), paying both sides once, caps and self-invites."""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.db.session import SessionFactory
from backend.app.models import CreditLedger, Notification, User
from backend.app.services import auth as auth_svc
from backend.app.services import referrals
from backend.app.services.email import sent_emails
from backend.app.services.outbox import Outbox

A = "/api/v1"


async def invite_code(actor) -> str:
    r = await actor.get(f"{A}/me/referral")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["link"].endswith(f"/r/{body['code']}")
    return body["code"]


async def sign_up_with(client, code: str | None, username: str, email: str | None = None) -> str:
    """Register as a newcomer who arrived through an invite link (the web app leaves the cookie). Returns user id."""
    client.cookies.clear()
    if code:
        client.cookies.set(referrals.COOKIE, code)
    r = await client.post(f"{A}/auth/register", json={
        "email": email or f"{username}@example.com", "password": "correct-horse-battery", "username": username})
    assert r.status_code == 201, r.text
    client.cookies.clear()
    return r.json()["user"]["id"]


async def verify_last_email(client) -> None:
    token = re.search(r"token=([A-Za-z0-9_\-]+)", sent_emails()[-1]["text"]).group(1)
    assert (await client.post(f"{A}/auth/verify-email", json={"token": token})).status_code == 200


async def credits(user_id: str) -> int:
    async with SessionFactory() as db:
        return await db.scalar(select(User.credits).where(User.id == uuid.UUID(user_id)))


async def test_both_sides_are_paid_once_after_the_newcomer_verifies(client, make_user):
    alice = await make_user("alice")
    code = await invite_code(alice)
    assert await invite_code(alice) == code  # stable

    who = (await client.get(f"{A}/referrals/{code}")).json()
    assert who["username"] == "alice" and who["invitee_credits"] == get_settings().referral_invitee_credits

    bob = await sign_up_with(client, code, "bob")
    assert await credits(bob) == 0 and await credits(alice.id) == 0  # nothing until the email is proven
    await verify_last_email(client)
    s = get_settings()
    assert await credits(bob) == s.referral_invitee_credits
    assert await credits(alice.id) == s.referral_inviter_credits

    # Settling again (a second verify link, a password reset) never pays twice.
    async with SessionFactory() as db:
        u = await db.get(User, uuid.UUID(bob))
        u.referral_settled_at = None
        await referrals.settle(db, Outbox(), u)
        await db.commit()
    assert await credits(bob) == s.referral_invitee_credits
    assert await credits(alice.id) == s.referral_inviter_credits

    async with SessionFactory() as db:
        n = await db.scalar(select(Notification).where(Notification.user_id == uuid.UUID(alice.id),
                                                       Notification.kind == "referral"))
        assert n is not None and n.link == "/invite"
    summary = (await alice.get(f"{A}/me/referral")).json()
    assert summary["rewarded"] == 1 and [i["username"] for i in summary["invited"]] == ["bob"]
    assert summary["invited"][0]["verified"] is True


async def test_inviter_rewards_stop_at_the_cap_but_newcomers_still_get_theirs(client, make_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "referral_max_rewards_per_user", 1)
    alice = await make_user("alice")
    code = await invite_code(alice)
    bob = await sign_up_with(client, code, "bob")
    await verify_last_email(client)
    carol = await sign_up_with(client, code, "carol")
    await verify_last_email(client)
    s = get_settings()
    assert await credits(alice.id) == s.referral_inviter_credits  # only the first invite paid the inviter
    assert await credits(bob) == await credits(carol) == s.referral_invitee_credits


async def test_inviting_yourself_pays_nothing(client, make_user):
    alice = await make_user("alice")
    async with SessionFactory() as db:  # alice's real address is a Gmail one
        await db.execute(User.__table__.update().where(User.id == uuid.UUID(alice.id))
                         .values(email="al.ice@gmail.com"))
        await db.commit()
    code = await invite_code(alice)
    me_again = await sign_up_with(client, code, "alice2", email="alice+2@googlemail.com")
    await verify_last_email(client)
    assert await credits(me_again) == 0 and await credits(alice.id) == 0


async def test_bad_or_unknown_codes_are_ignored(client, make_user):
    assert (await client.get(f"{A}/referrals/nope")).status_code == 404
    assert (await client.get(f"{A}/referrals/abcdefgh")).status_code == 404
    dave = await sign_up_with(client, "abcdefgh", "dave")
    await verify_last_email(client)
    async with SessionFactory() as db:
        assert (await db.get(User, uuid.UUID(dave))).referred_by_id is None
    assert referrals.valid_code("abcd2345") and not referrals.valid_code("ABCD2345") \
        and not referrals.valid_code("abcd0345")


async def test_google_sign_up_through_an_invite(client, make_user):
    alice = await make_user("alice")
    code = await invite_code(alice)
    async with SessionFactory() as db:
        user = await auth_svc.login_with_google(db, sub="g-123", email="gina@example.com", name="Gina",
                                                picture=None, referral_code=code)
        assert str(user.referred_by_id) == alice.id
        await referrals.settle(db, Outbox(), user)  # Google accounts arrive verified
        await db.commit()
        gina = str(user.id)
        # Signing in again later with a different code changes nothing.
        again = await auth_svc.login_with_google(db, sub="g-123", email="gina@example.com", name="Gina",
                                                 picture=None, referral_code="zzzzzzzz")
        assert str(again.referred_by_id) == alice.id
    assert await credits(gina) == get_settings().referral_invitee_credits
    async with SessionFactory() as db:
        keys = set((await db.scalars(select(CreditLedger.idempotency_key))).all())
    assert keys == {f"referral-invitee:{gina}", f"referral-inviter:{gina}"}


async def test_canonical_email():
    assert referrals.canonical_email("A.B+x@GoogleMail.com") == "ab@gmail.com"
    assert referrals.canonical_email("a.b+x@outlook.com") == "a.b@outlook.com"
