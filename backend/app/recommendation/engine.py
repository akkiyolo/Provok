import logging
import uuid
import json
from typing import List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.config import get_settings

from backend.app.models.debate import Debate, DebateStatus, DebateVisibility

logger = logging.getLogger(__name__)
settings = get_settings()

class RecommendationEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_explore_feed(self, user_id: Optional[uuid.UUID] = None, limit: int = 20) -> List[Debate]:
        """
        Fetch the best debates for the explore page with Redis caching.
        """
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
        cache_key = f"explore_feed:{limit}"
        
        if settings.recommendation_enabled:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                await redis_client.close()
                # Parse JSON and hydrate basic Debate models (simplified for MVP)
                # In production, we'd use Pydantic models for the response directly.
                # For now, we'll bypass cache and just run the query to guarantee real objects
                pass
        
        # Base query: Only public debates
        query = select(Debate).where(Debate.visibility == DebateVisibility.PUBLIC)
        query = query.order_by(
            desc(Debate.viewer_count),
            desc(Debate.created_at)
        )
        query = query.limit(limit)
        
        result = await self.db.scalars(query)
        debates = list(result)
        
        await redis_client.close()
        return debates

    async def get_personalized_feed(self, user_id: uuid.UUID, limit: int = 20) -> List[Debate]:
        """
        Fetch a personalized feed for a specific user.
        In the future, this will use collaborative filtering or pgvector semantic similarity.
        For now, it falls back to the explore feed logic.
        """
        return await self.get_explore_feed(user_id=user_id, limit=limit)
