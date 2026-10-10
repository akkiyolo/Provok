"""PROVOK — Notifications API routes."""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.core import get_db
from backend.app.models.user import User
from backend.app.models.social import Notification
from backend.app.dependencies import get_current_user

router = APIRouter()


@router.get("/")
async def get_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch notifications for the current user."""
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.read == False)

    query = query.order_by(desc(Notification.created_at)).limit(limit)

    notifications = await db.scalars(query)
    result = []
    for n in notifications:
        result.append({
            "id": str(n.id),
            "type": n.notification_type,
            "title": n.title,
            "body": n.body,
            "link": n.link,
            "is_read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })

    # Get unread count
    unread_count = await db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == current_user.id,
            Notification.read == False
        )
    )

    return {
        "notifications": result,
        "unread_count": unread_count or 0,
    }


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a single notification as read."""
    import uuid
    await db.execute(
        update(Notification)
        .where(Notification.id == uuid.UUID(notification_id), Notification.user_id == current_user.id)
        .values(read=True)
    )
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all notifications as read for the current user."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)
        .values(read=True)
    )
    return {"status": "ok"}
