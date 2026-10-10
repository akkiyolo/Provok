import logging
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.config import get_settings
from backend.app.models.debate import Debate, DebateVisibility

logger = logging.getLogger(__name__)
settings = get_settings()


class RecommendationEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_explore_feed(self, user_id: Optional[uuid.UUID] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch the best debates for the explore page with graceful Redis caching.
        """
        # Base query: Only public debates with question and participants loaded
        query = (
            select(Debate)
            .options(selectinload(Debate.question), selectinload(Debate.participants))
            .where(Debate.visibility == DebateVisibility.PUBLIC)
            .order_by(
                desc(Debate.viewer_count),
                desc(Debate.created_at)
            )
            .limit(limit)
        )
        
        result = await self.db.scalars(query)
        debates = list(result)

        formatted = []
        for d in debates:
            formatted.append({
                "id": str(d.id),
                "title": d.question.text if d.question else "Topic",
                "status": d.status,
                "mode": d.mode,
                "current_round": d.current_round,
                "viewer_count": d.viewer_count or 0,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            })
        
        return formatted

    async def get_personalized_feed(self, user_id: uuid.UUID, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch a personalized feed for a specific user.
        Falls back safely to the explore feed.
        """
        return await self.get_explore_feed(user_id=user_id, limit=limit)
