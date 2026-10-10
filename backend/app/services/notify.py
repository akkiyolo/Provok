"""In-app notifications (+ realtime push, + email for async moments)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Notification
from backend.app.realtime.publish import publish_user
from backend.app.services.outbox import Outbox


async def notify(db: AsyncSession, outbox: Outbox, user_id: uuid.UUID, kind: str, title: str, *,
                 body: str | None = None, link: str | None = None) -> None:
    n = Notification(user_id=user_id, kind=kind, title=title[:200], body=(body or "")[:500] or None, link=link)
    db.add(n)
    await db.flush()
    payload = {"id": str(n.id), "kind": kind, "title": n.title, "body": n.body, "link": link}

    async def _push() -> None:
        await publish_user(user_id, "notification", payload)

    outbox.add(_push)
