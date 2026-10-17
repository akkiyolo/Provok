"""Web push: subscribing, the endpoint allowlist, encrypted delivery, and dropping dead subscriptions."""
from __future__ import annotations

import base64
import json
import os

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import func, select

from backend.app.core.config import get_settings
from backend.app.db.session import SessionFactory
from backend.app.models import PushSubscription
from backend.app.services import push

A = "/api/v1"
FCM = "https://fcm.googleapis.com/fcm/send/"


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Device:
    """A browser's side of a push subscription: its key pair and auth secret."""

    def __init__(self, name: str) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.endpoint = FCM + name

    def subscription(self) -> dict:
        pub = self.key.public_key().public_bytes(serialization.Encoding.X962,
                                                 serialization.PublicFormat.UncompressedPoint)
        return {"endpoint": self.endpoint, "keys": {"p256dh": b64(pub), "auth": b64(self.auth)}}

    def decrypt(self, body: bytes) -> dict:
        return json.loads(http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"))


@pytest.fixture
def vapid(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", b64(pub))
    monkeypatch.setattr(s, "vapid_private_key", b64(key.private_numbers().private_value.to_bytes(32, "big")))
    return s


@pytest.fixture
def push_service(monkeypatch):
    """Stands in for FCM: records requests; endpoints listed in `gone` answer 410."""
    sent: list[httpx.Request] = []
    gone: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(410 if str(request.url) in gone else 201)

    real = httpx.AsyncClient
    monkeypatch.setattr(push.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return sent, gone


async def count_subs() -> int:
    async with SessionFactory() as db:
        return await db.scalar(select(func.count()).select_from(PushSubscription)) or 0


async def unsubscribe(actor, endpoint: str) -> httpx.Response:
    return await actor.client.request("DELETE", f"{A}/me/push-subscriptions", json={"endpoint": endpoint},
                                      headers=actor.h)


def test_endpoint_allowlist():
    ok = ["https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/x",
          "https://web.push.apple.com/QGx", "https://db5p.notify.windows.com/w/?token=1"]
    bad = ["http://fcm.googleapis.com/x", "https://fcm.googleapis.com.evil.com/x", "https://evil.com/x",
           "https://169.254.169.254/latest", "https://user:pw@fcm.googleapis.com/x",
           "https://fcm.googleapis.com:8443/x", "https://push.services.mozilla.com/x", "https://localhost/x",
           "not a url"]
    assert all(push.endpoint_allowed(u) for u in ok)
    assert not any(push.endpoint_allowed(u) for u in bad)


def test_payload_links_stay_on_site():
    assert push.make_payload("x", "t", None, "https://evil.com")["link"] == "/notifications"
    assert push.make_payload("x", "t", None, "//evil.com")["link"] == "/notifications"
    assert push.make_payload("x", "t", "b", "/d/1")["link"] == "/d/1"


async def test_push_is_off_without_vapid_keys(client, make_user, jobs):
    assert (await client.get(f"{A}/push/config")).json() == {"enabled": False, "public_key": None}
    alice, bob = await make_user("alice"), await make_user("bob")
    assert (await alice.post(f"{A}/me/push-subscriptions", Device("a").subscription())).status_code == 409
    await bob.post(f"{A}/users/alice/follow")
    assert "send_push" not in jobs.names()


async def test_subscribe_validates_and_upserts(client, make_user, vapid):
    assert (await client.get(f"{A}/push/config")).json() == {"enabled": True, "public_key": vapid.vapid_public_key}
    alice, bob = await make_user("alice"), await make_user("bob")
    phone = Device("phone")
    evil = {**phone.subscription(), "endpoint": "https://attacker.example/hook"}
    assert (await alice.post(f"{A}/me/push-subscriptions", evil)).status_code == 422
    assert (await alice.post(f"{A}/me/push-subscriptions", phone.subscription())).status_code == 200
    assert (await alice.post(f"{A}/me/push-subscriptions", phone.subscription())).status_code == 200
    assert await count_subs() == 1
    # The same browser signed in as someone else now belongs to them.
    assert (await bob.post(f"{A}/me/push-subscriptions", phone.subscription())).status_code == 200
    async with SessionFactory() as db:
        assert str(await db.scalar(select(PushSubscription.user_id))) == bob.id
    assert (await unsubscribe(alice, phone.endpoint)).status_code == 200
    assert await count_subs() == 1  # alice can't remove bob's device
    await unsubscribe(bob, phone.endpoint)
    assert await count_subs() == 0


async def test_notifications_and_dms_are_pushed_encrypted(client, make_user, vapid, jobs, push_service):
    sent, gone = push_service
    alice, bob = await make_user("alice"), await make_user("bob")
    phone, laptop = Device("phone"), Device("laptop")
    for d in (phone, laptop):
        await alice.post(f"{A}/me/push-subscriptions", d.subscription())

    await bob.post(f"{A}/users/alice/follow")
    await jobs.run()
    assert len(sent) == 2
    req = next(r for r in sent if str(r.url) == phone.endpoint)
    assert req.headers["Content-Encoding"] == "aes128gcm" and req.headers["Authorization"].startswith("vapid t=")
    assert int(req.headers["TTL"]) == vapid.push_ttl_seconds
    msg = phone.decrypt(req.content)
    assert msg["kind"] == "follow" and "followed you" in msg["title"] and msg["link"].startswith("/")

    sent.clear()
    gone.add(laptop.endpoint)  # the laptop's browser dropped the subscription
    c = (await bob.post(f"{A}/conversations/with/alice")).json()
    await bob.post(f"{A}/conversations/{c['id']}/messages", {"text": "Your move, champ"})
    await jobs.run()
    req = next(r for r in sent if str(r.url) == phone.endpoint)
    dm = phone.decrypt(req.content)
    assert dm["kind"] == "dm" and dm["body"] == "Your move, champ" and dm["link"] == f"/messages/{c['id']}"
    assert req.headers["Urgency"] == "high"
    assert await count_subs() == 1  # 410 Gone removed the laptop


async def test_account_deletion_drops_devices(client, make_user, vapid):
    alice = await make_user("alice")
    await alice.post(f"{A}/me/push-subscriptions", Device("phone").subscription())
    r = await alice.post(f"{A}/me/delete", {"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert await count_subs() == 0


async def test_keeps_only_the_newest_devices(client, make_user, vapid, monkeypatch):
    monkeypatch.setattr(vapid, "push_max_subscriptions_per_user", 2)
    alice = await make_user("alice")
    for i in range(4):
        await alice.post(f"{A}/me/push-subscriptions", Device(f"d{i}").subscription())
    async with SessionFactory() as db:
        endpoints = set((await db.scalars(select(PushSubscription.endpoint))).all())
    assert endpoints == {FCM + "d2", FCM + "d3"}
