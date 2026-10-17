"""Web push (VAPID, RFC 8030/8291/8292): store browsers' subscriptions and send them notifications.

The server POSTs to whatever endpoint a browser hands it, so endpoints must be https on a known push service
(`PUSH_ENDPOINT_HOSTS`); anything else is refused at subscribe time and again before sending.
"""
from __future__ import annotations

import json
import uuid
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

import httpx
from py_vapid import Vapid02
from pywebpush import WebPusher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.core.security import utcnow
from backend.app.db.session import session_scope
from backend.app.models import PushSubscription

log = get_logger("provok.push")

# Moments worth waking a phone for right away; everything else is delivered at normal priority.
_URGENT_KINDS = {"your_turn", "challenge", "opponent_joined", "dm"}
_GONE = {404, 410}


def endpoint_allowed(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or port not in (None, 443):
        return False
    for allowed in get_settings().push_hosts:
        if allowed.startswith("*."):
            if host.endswith(allowed[1:]) and host != allowed[2:]:
                return True
        elif host == allowed:
            return True
    return False


async def save_subscription(db: AsyncSession, user_id: uuid.UUID, *, endpoint: str, p256dh: str, auth: str,
                            user_agent: str | None) -> None:
    """Upsert by endpoint (a device that switched accounts moves to the new one), keeping the newest few."""
    sub = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if sub is None:
        db.add(PushSubscription(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth,
                                user_agent=(user_agent or "")[:300] or None))
    else:
        sub.user_id, sub.p256dh, sub.auth = user_id, p256dh, auth
        sub.user_agent = (user_agent or "")[:300] or None
    await db.flush()
    keep = get_settings().push_max_subscriptions_per_user
    stale = (await db.scalars(
        select(PushSubscription.id).where(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.created_at.desc(), PushSubscription.id.desc()).offset(keep)
    )).all()
    if stale:
        await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(stale)))


async def remove_subscription(db: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    await db.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id,
                                                    PushSubscription.endpoint == endpoint))


@lru_cache
def _vapid(private_key: str) -> Vapid02:
    return Vapid02.from_string(private_key=private_key)


def build_request(sub: PushSubscription, payload: dict[str, Any]) -> tuple[dict[str, str], bytes]:
    """Encrypt the payload for one subscription (aes128gcm) and sign the VAPID headers."""
    s = get_settings()
    info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
    encoded = WebPusher(info).encode(json.dumps(payload, ensure_ascii=False).encode(), "aes128gcm")
    parts = urlsplit(sub.endpoint)
    claims: dict[str, str | int] = {"aud": f"{parts.scheme}://{parts.netloc}", "sub": s.vapid_subject}
    headers = {str(k): str(v) for k, v in _vapid(s.vapid_private_key).sign(claims).items()}
    headers.update({
        "TTL": str(s.push_ttl_seconds),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "Urgency": "high" if payload.get("kind") in _URGENT_KINDS else "normal",
    })
    if payload.get("tag"):
        headers["Topic"] = str(payload["tag"])[:32]  # a newer push with the same topic replaces an undelivered one
    return headers, encoded["body"]


def make_payload(kind: str, title: str, body: str | None, link: str | None, tag: str | None = None) -> dict[str, Any]:
    safe_link = link if link and link.startswith("/") and not link.startswith("//") else "/notifications"
    return {"kind": kind, "title": title[:120], "body": (body or "")[:240], "link": safe_link,
            "tag": tag or kind}


async def send_to_user(user_id: uuid.UUID, payload: dict[str, Any]) -> int:
    """Deliver to every device the user subscribed. Returns how many push services accepted it."""
    if not get_settings().push_enabled:
        return 0
    async with session_scope() as db:
        subs = (await db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id))).all()
        if not subs:
            return 0
        delivered, gone = 0, []
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            for sub in subs:
                if not endpoint_allowed(sub.endpoint):
                    gone.append(sub.id)
                    continue
                try:
                    headers, body = build_request(sub, payload)
                    resp = await client.post(sub.endpoint, headers=headers, content=body)
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("push_send_failed", subscription=str(sub.id), error=str(exc))
                    continue
                if resp.status_code in _GONE:
                    gone.append(sub.id)
                elif resp.status_code < 300:
                    delivered += 1
                    sub.last_success_at = utcnow()
                else:
                    log.warning("push_rejected", subscription=str(sub.id), status=resp.status_code,
                                body=resp.text[:200])
        if gone:
            await db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
    return delivered
