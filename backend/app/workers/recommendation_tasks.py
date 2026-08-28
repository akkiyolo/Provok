"""PROVOK — Recommendation background tasks."""
from backend.app.workers.celery_app import celery_app


import asyncio
import logging
from typing import List
from uuid import UUID

from backend.app.database.core import async_session_factory
from backend.app.config import get_settings
from backend.app.recommendation.engine import RecommendationEngine

logger = logging.getLogger(__name__)
settings = get_settings()

async def _cache_recommendations_async(user_id: str):
    """Async handler to compute and cache personalized feeds."""
    async with async_session_factory() as session:
        engine = RecommendationEngine(session)
        
        # 1. Compute personalized feed
        debates = await engine.get_personalized_feed(user_id=UUID(user_id), limit=20)
        
        # 2. Serialize simple representation for Redis
        # (Using minimal representation for fast cache retrieval)
        serialized_feed = [
            {
                "id": str(d.id),
                "viewer_count": d.viewer_count,
                "status": d.status.value,
                "created_at": d.created_at.isoformat() if d.created_at else None
            }
            for d in debates
        ]
        
        # 3. Save to Redis Cache (DB 1)
        import redis.asyncio as aioredis
        import json
        redis_client = aioredis.from_url(settings.redis_cache_url)
        cache_key = f"user_feed:{user_id}"
        
        await redis_client.setex(
            cache_key,
            settings.recommendation_cache_seconds, # Default 5 mins
            json.dumps(serialized_feed)
        )
        await redis_client.close()
        
        logger.info(f"Cached personalized feed for user {user_id} ({len(debates)} debates)")

@celery_app.task(name="recommendation.generate", bind=True)
def generate_recommendations(self, user_id: str):
    """Generate personalized recommendations for a user in the background."""
    if not settings.recommendation_enabled:
        return
    asyncio.run(_cache_recommendations_async(user_id))
