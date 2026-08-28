"""PROVOK — Feed / Discovery API routes."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database.core import get_db
from backend.app.recommendation.engine import RecommendationEngine
from backend.app.dependencies import get_current_user_optional, get_current_user
from backend.app.models.user import User

router = APIRouter()

@router.get("/feed")
async def get_feed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, le=100)
):
    """Personalized feed of debates for the logged-in user."""
    import redis.asyncio as aioredis
    import json
    from backend.app.config import get_settings
    
    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    cache_key = f"user_feed:{current_user.id}"
    
    cached_feed = await redis_client.get(cache_key)
    await redis_client.close()
    
    if cached_feed:
        # We have a pre-computed feed from Celery!
        # In a real app we might hydrate full Pydantic models here.
        return {"debates": json.loads(cached_feed), "source": "cache"}
        
    # Fallback to synchronous computation
    engine = RecommendationEngine(db)
    debates = await engine.get_personalized_feed(user_id=current_user.id, limit=limit)
    
    # Trigger background job to warm cache for next time
    from backend.app.workers.recommendation_tasks import generate_recommendations
    generate_recommendations.delay(str(current_user.id))
    
    return {"debates": debates, "source": "db"}

@router.get("/live")
async def get_live(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100)
):
    """Get currently live/active debates."""
    from backend.app.models.debate import Debate, DebateStatus
    from sqlalchemy import select, desc
    
    query = select(Debate).where(Debate.status.in_([DebateStatus.LIVE, DebateStatus.READY, DebateStatus.WAITING]))
    query = query.order_by(desc(Debate.viewer_count)).limit(limit)
    result = await db.scalars(query)
    
    return {"debates": list(result)}

@router.get("/explore")
async def get_explore(
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    limit: int = Query(20, le=100)
):
    """Explore feed of trending and popular debates."""
    engine = RecommendationEngine(db)
    user_id = current_user.id if current_user else None
    debates = await engine.get_explore_feed(user_id=user_id, limit=limit)
    return {"debates": debates}
