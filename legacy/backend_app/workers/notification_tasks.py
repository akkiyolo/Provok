"""PROVOK — Notification background tasks."""
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="notification.send")
def send_notification(user_id: str, notification_type: str, title: str, body: str = None, link: str = None, debate_id: str = None):
    """Create and deliver a notification. Phase 8."""
    pass
