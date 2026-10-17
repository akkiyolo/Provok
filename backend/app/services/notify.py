"""In-app notifications (+ realtime, + web push to the user's devices, + email for async moments)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models import Notification
from backend.app.realtime.publish import publish_user
from backend.app.services import push
from backend.app.services.outbox import Outbox
from backend.app.workers.queue import enqueue


async def notify(db: AsyncSession, outbox: Outbox, user_id: uuid.UUID, kind: str, title: str, *,
                 body: str | None = None, link: str | None = None) -> None:
    n = Notification(user_id=user_id, kind=kind, title=title[:200], body=(body or "")[:500] or None, link=link)
    db.add(n)
    await db.flush()
    payload = {"id": str(n.id), "kind": kind, "title": n.title, "body": n.body, "link": link}

    async def _push() -> None:
        await publish_user(user_id, "notification", payload)

    outbox.add(_push)
    queue_push(outbox, user_id, push.make_payload(kind, n.title, n.body, link), job_id=f"push:{n.id}")


def queue_push(outbox: Outbox, user_id: uuid.UUID, payload: dict, *, job_id: str) -> None:
    if not get_settings().push_enabled:
        return

    async def _web_push() -> None:
        await enqueue("send_push", str(user_id), payload, job_id=job_id)

    outbox.add(_web_push)
